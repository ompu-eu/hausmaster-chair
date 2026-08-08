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
NOW=$($PY -c "
import json,sys
try:
    r=json.load(open('$ARR/arrival_log.json'))['runs'][-1]
    print(r['unreachable_total'])
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
