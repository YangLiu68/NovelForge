#!/usr/bin/env bash
# Bring up the Docker Compose stack and use it the way a person would: the API answers, the
# database is migrated, a sample imports and its contradiction report has the planted findings,
# and the frontend is served by nginx with the API proxied. Used by CI and runnable locally.
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose up -d
api=http://127.0.0.1:8000
web=http://127.0.0.1:8080

for i in $(seq 1 60); do
  if curl -fsS "$api/api/health" > /dev/null 2>&1; then break; fi
  [ "$i" = 60 ] && { echo "API did not come up"; exit 1; }
  sleep 2
done
echo "health: $(curl -fsS "$api/api/health")"

novel=$(curl -fsS -X POST "$api/api/samples/lanternfall/import" | python3 -c 'import json,sys; print(json.load(sys.stdin)["novel_id"])')
echo "imported lanternfall as $novel"
findings=$(curl -fsS "$api/api/novels/$novel/contradictions" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["findings"]))')
echo "contradiction findings: $findings"
[ "$findings" -ge 4 ] || { echo "expected the 4 planted findings"; exit 1; }

zh=$(curl -fsS -X POST "$api/api/samples/wugang-xinzha/import" | python3 -c 'import json,sys; print(json.load(sys.stdin)["novel_id"])')
curl -fsS "$api/api/novels/$zh/contradictions" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("Chinese sample findings:", len(d["findings"]))
assert len(d["findings"]) >= 7, "expected the 7 planted findings"
assert any("一" <= ch <= "鿿" for ch in d["findings"][0]["explanation"]), "explained in Chinese"
'

curl -fsS "$web/" | grep -q '<div id="root">' && echo "frontend: index served"
curl -fsS "$web/api/health" > /dev/null && echo "frontend: /api proxied to the backend"
echo "compose smoke test passed"
