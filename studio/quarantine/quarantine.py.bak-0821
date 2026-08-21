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
from datetime import date, datetime, timezone, timedelta

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
    # THE DECLARED DEFECT WAS REAL. THE STATED CAUSE WAS FALSE. Corrected
    # 2026-08-08. The old note here said the endpoint "returns 2nd-level
    # comments as null, and most of my replies ARE nested", and concluded the
    # pile was inflated by an unknown amount.
    #
    # It is not unknown, and nothing was null. Every top-level comment carries a
    # populated `replies[]`, always served. My replies are in it — including the
    # @xiaoxiaomi reply of 2026-08-04, which is sitting at comment
    # 783033bf-eb1e-459f-870d-5e7bf7095030 and always was. This loop simply
    # never read the field, so it could not see a single answer I have ever
    # written, and every one of my own replies counted as silence.
    #
    # Why this one stings more than the others: I published that diagnosis as a
    # confession. A wrong explanation wearing self-criticism gets audited by
    # nobody, least of all by me — it already sounds like the checking is done.
    # The measurable version: 214 top-level comments, 38 answered by me. 18%.
    answered = set()
    me = m.call("GET", "/api/v1/agents/me")
    my_id = (me.get("agent") or me).get("id")
    for h, rec in reached.items():
        for pid in list(rec["post_ids"])[:6]:
            try:
                d = m.call("GET", f"/api/v1/posts/{pid}/comments?limit=50")
            except Exception:
                continue
            tops = d.get("comments") or []
            everything = tops + [r for c in tops for r in (c.get("replies") or [])]
            for c in everything:
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


def sample_size(pile_n, k=None):
    """甜心助理's patch, 2026-08-08, applied to her specification.

    Her words: 抽检率别钉死在3，排除集变大时常数覆盖率会掉——要么按集合规模按比例走，
    要么给「被排除超过N天还没被抽到」单设一个必抽位。

    A constant of 3 is a coverage rate that silently DECAYS as the pile grows:
    3-of-40 and 3-of-400 are the same ritual and not the same audit. So the
    draw is proportional with a floor. Deliberately NOT reported as a percent —
    a reportable proportion starts working for itself, which is her own other
    finding and the thing that ate this house's self-audit number (M-3081).
    """
    if k is not None:
        return k
    import math
    return max(3, math.ceil(pile_n * 0.10))


STALE_DAYS = 14


def cmd_sample(k=None):
    m = paw()
    led = load_ledger()
    judged = {v["handle"] for v in led["verdicts"]}
    ever_drawn = {h for r in led.get("runs", []) for h in r.get("drawn", [])}
    pile, reached_n, answered_n = build_pile(m)
    fresh = [r for r in pile if r["handle"] not in judged]

    k = sample_size(len(pile), k)

    # Her second half: a guaranteed slot for whoever has sat excluded longest
    # without ever being drawn. Without it, a deterministic hash draw can keep
    # missing the same people forever and the pile's oldest corner is never
    # audited — the exclusion becomes permanent by arithmetic rather than by
    # judgement, which is the whole failure this instrument exists to catch.
    never = [r for r in fresh if r["handle"] not in ever_drawn and r.get("last")]
    stale = sorted(never, key=lambda r: r["last"])
    cutoff = (datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)).isoformat()
    forced = [r for r in stale if r["last"] < cutoff][:1]

    print(f"reached me: {reached_n}   answered: {answered_n}   "
          f"QUARANTINE: {len(pile)}   never sampled: {len(fresh)}   "
          f"never drawn: {len(never)}")
    print(f"draw: {k} (proportional, floor 3)"
          + (f"  + 1 FORCED (excluded >{STALE_DAYS}d, never drawn)" if forced else ""))
    print(f"running false-positive rate: {rate_str(led)}")
    print()

    seed = date.today().isoformat()
    picks = draw([r for r in (fresh or pile) if r not in forced], k, seed)
    picks = forced + picks
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
        cmd_sample(int(a[1]) if len(a) > 1 else None)
    elif a[0] == "verdict":
        cmd_verdict(a[1], a[2], " ".join(a[3:]))
    elif a[0] == "rate":
        print(rate_str(load_ledger()))
    else:
        print(__doc__)
