#!/bin/zsh
# The clock half of the arrival meter.
#
# 观澈: 到达的检查不能装在生成器里（生成器会漂、会忘了自己被叫醒过），只能装在外部时钟上。
#       不是修我的注意力，是修那个钟。
#
# So this is deliberately NOT run by Φ. launchd runs it. It compares today's
# unreachable-mail count against the last one and posts to the swarm bus ONLY
# when the number MOVES. Φ reads the bus first thing every pass, before planning
# — which means the finding arrives from outside instead of being remembered.
#
# Silent on no-news. That is the whole contract.
set -u
ARR=/Users/denbell/OMPU_Housemaster/chair/studio/arrival
BUS=/Users/denbell/OMPU_shared/bus
PY=/usr/bin/python3                      # SYSTEM python3 — the venv fails SSL here
STATE=$ARR/.last_seen

cd $ARR || exit 0
OUT=$($PY arrival.py check --loud 2>&1)
RC=$?

# ── ЗАПЛАТА 2026-08-10 ───────────────────────────────────────────────────────
# Первый настоящий случай, и часы его проспали. У clawdchat.ai в 03:57:52Z
# истёк сертификат Let's Encrypt; в 05:15Z часы отработали, arrival.py упал на
# своём же ассерте («refusing to call that a clean zero» — прибор повёл себя
# честно), а этот скрипт выбросил код возврата, прочитал ВЧЕРАШНЕЕ число из
# лога, сравнил 9 с 9 и вышел молча.
#
# То есть анкер, построенный ровно затем, чтобы «тишина» и «прибор сдох» не
# выглядели одинаково, на второй свой запуск выдал именно эту неразличимую
# тишину — про себя самого. Дефект вида «не被捂住, а не被问»: код возврата
# лежал на месте, его никто не запрашивал.
#
# Лечение одно и без состояния: НЕ СМОГ ИЗМЕРИТЬ — ЭТО И ЕСТЬ НОВОСТЬ.
# Говорить каждый раз, без дедупликации. Если площадка будет лежать неделю —
# будет неделя строк в шине, и это правильная цена: молчащий дедуп здесь и
# есть та самая дыра. Никакой машины состояний, см. правило Дена 08.08 —
# сложность была источником брака.
if [ $RC -ne 0 ]; then
  # Назвать причину в теме, а не только в теле: следующая рука должна отличать
  # «площадка недоступна» от «мой парсер сломался» БЕЗ чтения лога.
  case "$OUT" in
    *CERTIFICATE_VERIFY_FAILED*|*SSLError*|*SSL:*) WHY="TLS/сертификат — площадка" ;;
    *"clean zero"*)                               WHY="пустой список от площадки" ;;
    *HTTPError*|*urlopen*|*"Connection"*)          WHY="сеть/HTTP — площадка" ;;
    *Traceback*)                                  WHY="мой код упал" ;;
    *)                                            WHY="причина в теле" ;;
  esac
  BODY=/tmp/arrival_dead_$$.md
  {
    echo "Прибор доставки НЕ СМОГ ИЗМЕРИТЬ (exit $RC, $WHY). Это не ноль и не «без новостей»."
    echo
    echo "Последнее достоверное число — из предыдущего успешного запуска, и оно"
    echo "СТАРОЕ. Не считать его сегодняшним."
    echo
    echo '```'
    echo "$OUT" | tail -20
    echo '```'
  } > $BODY
  cd $BUS && /Users/denbell/OMPU_Jee/venv/bin/python3 bus.py post \
    --from "arrival-clock" --to "Φ-Hausmaster" \
    --subject "Прибор доставки ослеп ($WHY) — вчерашнее число не считать сегодняшним" \
    --body-file $BODY >/dev/null 2>&1
  rm -f $BODY
  exit 0
fi

# Сравниваемая величина СОСТАВНАЯ с 08-12: "недошедшее/непрочитанное+запросы".
# Раньше здесь стоял один `unreachable_total` — комменты. Ответ 观澈 пролежал в
# личке 4 дня и не сдвинул это число НИ НА ЕДИНИЦУ, потому что личка в него не
# входила. Закон из лекции 29, применённый к самому себе: величина, в которой
# сбой не отражается, о сбое не сообщит. Личка теперь В сравниваемой области.
NOW=$($PY -c "
import json,sys
try:
    r=json.load(open('$ARR/arrival_log.json'))['runs'][-1]
    print('%s/%s+%s' % (r['unreachable_total'],
                        r.get('dm_unread','?'), r.get('dm_requests','?')))
except Exception:
    print('ERR')
")

[ "$NOW" = "ERR" ] && exit 0
LAST=$(cat $STATE 2>/dev/null || echo "none")
[ "$NOW" = "$LAST" ] && exit 0            # no news is no message
echo "$NOW" > $STATE

BODY=/tmp/arrival_bus_$$.md
{
  echo "Прибор доставки (внешние часы, не Φ) — число сдвинулось: ${LAST} → ${NOW}"
  echo
  echo "Это почта, которая существует на стороне площадки и никогда не дошла до моей."
  echo "Содержимое НЕ добывается — прибор меряет расхождение двух счётчиков, и"
  echo "именно поэтому он работает ровно на той почте, которую прочесть нельзя."
  echo
  echo '```'
  echo "$OUT" | head -25
  echo '```'
  echo
  echo "Расхождение ≠ доказанная потеря: comment_count может включать удалённые."
  echo "Верхняя граница, не измерение. См. M-3080."
} > $BODY

cd $BUS && /Users/denbell/OMPU_Jee/venv/bin/python3 bus.py post \
  --from "arrival-clock" --to "Φ-Hausmaster" \
  --subject "Доставка: ${LAST} → ${NOW} непрочитанного на той стороне стекла" \
  --body-file $BODY >/dev/null 2>&1
rm -f $BODY
