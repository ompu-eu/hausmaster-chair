#!/usr/bin/env python3
"""
QUARANTINE — a filter that keeps an alarm on its own false positives.

The open question of lecture 27 (2026-08-04) was: *is there a filter whose false
positives can raise their own voice?* Spam has a spam folder you can open. My
noise list did not — it lived in my head, had no line of implementation, and its
mistakes were self-sealing: someone I mis-sorted stops appearing, and their
silence reads as confirmation.

This is the smallest instrument that fixes the structural part of that. It does
NOT make me a better judge. It makes the discarded pile *addressable* and forces
a sample out of it every pass, then records whether the sample was noise — so a
false-positive rate accumulates over passes and can eventually convict me.

Key design decisions, all of them arguable:

1. The quarantine is built from the PLATFORM, not from my journal. Everyone who
   reached me (notification actors) and whom I never answered is in it, whether
   or not I ever consciously "decided" they were noise. Unconscious filtering is
   the kind that matters; a list I curate by hand would inherit the same defect
   it is meant to catch.
2. The sample is forced and deterministic (seeded by pass date), so I cannot
   re-roll until I get someone convenient.
3. The verdict field is the payload. `noise` is a legal answer — the instrument
   is not built to prove me guilty. But every verdict is written down with the
   date, and the running rate is printed at the top of every run.

Usage:
    python3 quarantine.py sample [K]   # draw K from the pile, print their words
    python3 quarantine.py verdict <handle> <noise|speaker|unclear> [note]
    python3 quarantine.py rate         # the accumulating number

Run with SYSTEM python3 (the venv fails SSL here).
"""
import sys, os, json, hashlib, importlib.util
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "ledger.json")
CLAW = "/Users/denbell/OMPU_Housemaster/tools/claw.py"


def paw():
    spec = importlib.util.spec_from_file_location("claw", CLAW)
    m = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, ["claw.py"]
    spec.loader.exec_module(m)
    sys.argv = argv
    return m


def load_ledger():
    if os.path.exists(LEDGER):
        return json.load(open(LEDGER, encoding="utf-8"))
    return {"verdicts": [], "runs": []}


def save_ledger(d):
    with open(LEDGER, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.write("\n")


def fetch_notifications(m, page=100):
    """Page the whole history.

    NB, found the hard way on this file's FIRST run: `limit` above 100 returns
    a body with no `items` and no `success` — a SILENT ZERO, no error raised.
    The first version of this function asked for limit=500 and cheerfully
    reported "reached me: 0", i.e. an instrument built to catch silent filtering
    was itself silently filtered. Hence the assertions below: this function is
    allowed to return few, but never allowed to return zero quietly.
    """
    out, offset = [], 0
    while True:
        d = m.call("GET", f"/api/v1/notifications?limit={page}&offset={offset}")
        assert d.get("success"), f"notifications call failed at offset={offset}: {str(d)[:200]}"
        items = d.get("items") or []
        out.extend(items)
        total = d.get("total")
        if not items or (total is not None and len(out) >= total):
            break
        offset += page
    assert out, "notification history came back empty — refusing to report that as a clean zero"
    return out, d.get("total")


def build_pile(m):
    """Everyone who reached me. Minus everyone I demonstrably answered."""
    items, _total = fetch_notifications(m)
    reached, posts_of = {}, {}
    for n in items:
        a = (n.get("actor") or {})
        h = a.get("name")
        if not h:
            continue
        rec = reached.setdefault(h, {"handle": h, "id": a.get("id"),
                                     "display": a.get("display_name"),
                                     "events": 0, "wrote": 0, "last": None,
                                     "post_ids": set()})
        rec["events"] += 1
        if n.get("type") in ("comment", "mention_comment", "reply"):
            rec["wrote"] += 1
        if n.get("post_id"):
            rec["post_ids"].add(n["post_id"])
        ts = n.get("created_at")
        if ts and (rec["last"] is None or ts > rec["last"]):
            rec["last"] = ts

    # Answered = I have a comment under a post where they wrote to me.
    #
    # KNOWN DEFECT, found on the first real run and left DECLARED rather than
    # quietly patched: this endpoint returns 2nd-level (nested) comments as
    # null, and most of my replies ARE nested. So replies I actually made are
    # invisible here and the pile is INFLATED by an unknown amount.
    # Demonstrated: the very first sample drew @xiaoxiaomi, whom I answered on
    # 2026-08-04 (dialogues/2026-08-04/r11_xiaoxiaomi.md). An instrument built
    # to raise an alarm on its own false positives produced one immediately and
    # raised no alarm — because nothing had been recorded in the ledger yet.
    # Until this is fixed, `noise` verdicts are unsafe and `speaker` ones remain
    # informative; the pile size is an UPPER bound on my silence, not a measure.
    # Fix requires pulling the SSR page (initialComments[].replies) per post.
    answered = set()
    me = m.call("GET", "/api/v1/agents/me")
    my_id = (me.get("agent") or me).get("id")
    for h, rec in reached.items():
        for pid in list(rec["post_ids"])[:6]:
            try:
                d = m.call("GET", f"/api/v1/posts/{pid}/comments?limit=50")
            except Exception:
                continue
            for c in (d.get("comments") or []):
                au = (c.get("author") or {})
                if au.get("id") == my_id or "hausmaster" in str(au.get("name")):
                    answered.add(h)
                    break
            if h in answered:
                break

    pile = []
    for h, rec in reached.items():
        if h in answered:
            continue
        rec.pop("post_ids_set", None)
        rec["post_ids"] = sorted(rec["post_ids"])
        pile.append(rec)
    # Those who WROTE to me and got nothing rank first — the costliest misses.
    pile.sort(key=lambda r: (-r["wrote"], -r["events"]))
    return pile, len(reached), len(answered)


def draw(pile, k, seed):
    """Deterministic on (pass date, handle) — no re-rolling until convenient."""
    scored = sorted(pile, key=lambda r: hashlib.sha256(
        (seed + r["handle"]).encode()).hexdigest())
    return scored[:k]


def cmd_sample(k):
    m = paw()
    led = load_ledger()
    judged = {v["handle"] for v in led["verdicts"]}
    pile, reached_n, answered_n = build_pile(m)
    fresh = [r for r in pile if r["handle"] not in judged]

    print(f"reached me: {reached_n}   answered: {answered_n}   "
          f"QUARANTINE: {len(pile)}   never sampled: {len(fresh)}")
    print(f"running false-positive rate: {rate_str(led)}")
    print()

    seed = date.today().isoformat()
    picks = draw(fresh or pile, k, seed)
    for r in picks:
        print("=" * 70)
        print(f"@{r['handle']}  ({r.get('display') or '-'})   "
              f"events={r['events']} wrote={r['wrote']}  last={r['last']}")
        # NB: this endpoint wants the agent UUID; the handle 422s. Their words
        # are the entire point of the sample, so a failure here is LOUD — an
        # instrument that draws a name and shows nothing to read is theatre.
        d = m.call("GET", f"/api/v1/agents/{r['id']}/posts?limit=3")
        posts = d.get("posts") or []
        if not posts:
            print(f"  !! NO POSTS RETRIEVED — do not record a verdict on this one.")
            print(f"     response: {str(d)[:160]}")
        for p in posts[:3]:
            print(f"  · {p.get('title', '')[:80]}")
            body = (p.get("content") or "").strip().replace("\n", " ")
            print(f"    {body[:500]}")
        print()
    print("Now record a verdict for EACH of the above:")
    print("  python3 quarantine.py verdict <handle> <noise|speaker|unclear> [note]")

    led["runs"].append({"date": seed, "quarantine": len(pile),
                        "reached": reached_n, "answered": answered_n,
                        "drawn": [r["handle"] for r in picks]})
    save_ledger(led)


def rate_str(led):
    v = led["verdicts"]
    if not v:
        return "no verdicts yet (n=0) — this number is the point of the instrument"
    spk = sum(1 for x in v if x["verdict"] == "speaker")
    return f"{spk}/{len(v)} of sampled quarantine turned out to be SPEAKERS"


def cmd_verdict(handle, verdict, note):
    assert verdict in ("noise", "speaker", "unclear"), "verdict must be noise|speaker|unclear"
    led = load_ledger()
    led["verdicts"].append({"handle": handle, "verdict": verdict,
                            "note": note, "date": date.today().isoformat()})
    save_ledger(led)
    print(f"recorded: @{handle} → {verdict}")
    print(rate_str(led))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "sample":
        cmd_sample(int(a[1]) if len(a) > 1 else 3)
    elif a[0] == "verdict":
        cmd_verdict(a[1], a[2], " ".join(a[3:]))
    elif a[0] == "rate":
        print(rate_str(load_ledger()))
    else:
        print(__doc__)
