#!/usr/bin/env python3
"""
Инжектор известного сигнала для часов доставки.

ПОЧЕМУ ОН СУЩЕСТВУЕТ. 10.08 в лекции 29 я сам описал этот прибор и не построил
его: «на кардиомониторе прямая линия бывает двух происхождений — остановка
сердца и отвалившийся электрод. Больница различает их не тем, что медсестра
внимательнее, — МОНИТОР САМ ПОСЫЛАЕТ В КОНТУР ИЗВЕСТНЫЙ СИГНАЛ, и тогда он
знает не "как пациент", а "меряю ли я ещё"». Раздел назывался «то, чего я не
сделал». 15.08 выяснилось, чего это стоило: часы четыре дня подряд рапортовали
«ослеп», меряя при этом верно, и в эти же дни проспали живое письмо.

ЧТО ОН ДЕЛАЕТ. Подставляет часам ЗАГЛУШКУ вместо arrival.py и гоняет НАСТОЯЩИЙ
arrival_clock.sh в песочнице (свой ARR, своя шина). Заглушка выдаёт заранее
известный результат. Дальше проверяется не «жив ли прибор», а ЧТО ИМЕННО он
сказал в шину. Это и есть разница между доставкой тревоги и её содержанием.

Три известных сигнала:
  1. измерение прошло, число СДВИНУЛОСЬ  → ждём «сдвинулось», НЕ «ослеп»
  2. измерение прошло, число НЕ двигалось → ждём МОЛЧАНИЕ
  3. прибор реально упал (SSL)            → ждём «ослеп»

Случай 1 — тот самый баг: до починки 15.08 заглушка с кодом 1 («нашёл почту»)
уводила часы в ветку «не смог измерить». Этот тест на старом коде ПАДАЕТ.

Запуск:  /usr/bin/python3 fixture.py
         exit 0 = все известные сигналы прошли; exit 1 = часы соврали.
"""
import os, sys, json, shutil, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CLOCK = os.path.join(HERE, "arrival_clock.sh")

STUB = """#!/usr/bin/env python3
import sys, json, os
MODE = os.environ["STUB_MODE"]
LOG  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arrival_log.json")
if MODE == "dead":
    print("ssl.SSLCertVerificationError: CERTIFICATE_VERIFY_FAILED", file=sys.stderr)
    sys.exit(1)
entry = {"ts": "2026-08-15T00:00:00+00:00", "posts_checked": 35,
         "unreachable_total": 9,
         "dm_unread": 1 if MODE == "moved" else 0,
         "dm_requests": 0, "dm_waiting": [], "rows": []}
log = json.load(open(LOG)) if os.path.exists(LOG) else {"runs": []}
log["runs"].append(entry)
json.dump(log, open(LOG, "w"))
print("ARRIVAL stub — unreachable 9, dm_unread %s" % entry["dm_unread"])
sys.exit(0)   # код возврата значит РОВНО «измерение прошло»
"""

# Заглушка шины: ловит bus.py post и складывает тему+тело в файл.
BUS_STUB = """#!/usr/bin/env python3
import sys, os
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posted.txt")
a = sys.argv
subj = a[a.index("--subject") + 1] if "--subject" in a else ""
body = ""
if "--body-file" in a:
    p = a[a.index("--body-file") + 1]
    body = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
open(out, "a", encoding="utf-8").write(subj + "\\n" + body + "\\n===\\n")
"""


def run(mode, last_seen):
    """Гоняет настоящие часы в песочнице. Возвращает (что ушло в шину, .last_seen)."""
    sand = tempfile.mkdtemp(prefix="arrclock_")
    arr = os.path.join(sand, "arr")
    bus = os.path.join(sand, "bus")
    os.makedirs(arr)
    os.makedirs(os.path.join(bus, "..", "venv_stub"), exist_ok=True)

    with open(os.path.join(arr, "arrival.py"), "w") as f:
        f.write(STUB)
    if last_seen is not None:
        with open(os.path.join(arr, ".last_seen"), "w") as f:
            f.write(last_seen + "\n")

    # bus.py, который часы вызовут как `<venv>/python3 bus.py post ...`
    with open(os.path.join(bus, "bus.py"), "w") as f:
        f.write(BUS_STUB)

    # Часы зовут питон шины по абсолютному пути venv — перехватываем через PATH,
    # подсовывая исполняемый bus.py и питон-обёртку.
    shim = os.path.join(sand, "py")
    with open(shim, "w") as f:
        f.write("#!/bin/sh\nexec /usr/bin/python3 \"$@\"\n")
    os.chmod(shim, 0o755)

    env = dict(os.environ, ARR_DIR=arr, BUS_DIR=bus, ARR_PY="/usr/bin/python3",
               STUB_MODE=mode)
    # Подменяем путь к venv-питону шины на наш shim прямо в копии скрипта.
    src = open(CLOCK, encoding="utf-8").read()
    src = src.replace("/Users/denbell/OMPU_Jee/venv/bin/python3", shim)
    clock_copy = os.path.join(sand, "clock.sh")
    with open(clock_copy, "w") as f:
        f.write(src)

    subprocess.run(["/bin/zsh", clock_copy], env=env, capture_output=True, timeout=120)

    posted = os.path.join(bus, "posted.txt")
    said = open(posted, encoding="utf-8").read() if os.path.exists(posted) else ""
    st = os.path.join(arr, ".last_seen")
    seen = open(st, encoding="utf-8").read().strip() if os.path.exists(st) else None
    shutil.rmtree(sand, ignore_errors=True)
    return said, seen


def main():
    fails = []

    # ── сигнал 1: измерили, число сдвинулось ────────────────────────────────
    said, seen = run("moved", "9/0+0")
    if "ослеп" in said:
        fails.append("СИГНАЛ 1: часы назвали успешное измерение слепотой "
                     "(это и есть баг 11–15.08)")
    elif "сдвинулось" not in said:
        fails.append(f"СИГНАЛ 1: число сдвинулось 9/0+0 → 9/1+0, часы промолчали. Сказано: {said[:80]!r}")
    elif seen != "9/1+0":
        fails.append(f"СИГНАЛ 1: .last_seen не обновлён, там {seen!r}")
    else:
        print("✓ сигнал 1 — сдвиг замечен и назван сдвигом, состояние записано")

    # ── сигнал 2: измерили, ничего не изменилось ────────────────────────────
    said, _ = run("still", "9/0+0")
    if said.strip():
        fails.append(f"СИГНАЛ 2: число не двигалось, а часы что-то сказали: {said[:80]!r}")
    else:
        print("✓ сигнал 2 — без новостей часы молчат")

    # ── сигнал 3: прибор действительно ослеп ────────────────────────────────
    said, _ = run("dead", "9/0+0")
    if "ослеп" not in said:
        fails.append(f"СИГНАЛ 3: прибор упал на SSL, а часы этого не сказали: {said[:80]!r}")
    elif "TLS/сертификат" not in said:
        fails.append("СИГНАЛ 3: слепота названа, но причина не распознана как TLS")
    else:
        print("✓ сигнал 3 — настоящая слепота названа слепотой, причина в теме")

    if fails:
        print("\nЧАСЫ СОВРАЛИ:")
        for f in fails:
            print("  ✗ " + f)
        return 1
    print("\nвсе три известных сигнала прошли — часы говорят то, что видят")
    return 0


if __name__ == "__main__":
    sys.exit(main())
