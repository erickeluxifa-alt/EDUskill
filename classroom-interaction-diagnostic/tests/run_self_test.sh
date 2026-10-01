#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
out=$(python3 "$ROOT/scripts/diagnose.py" < "$ROOT/examples/sample.json")
printf '%s' "$out" | python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["summary"]["student_count"] == 5; assert x["summary"]["tiers"]["sufficient"] == 1; assert x["summary"]["attendance"]["absent"] == 1; assert x["side_effects"]["writes"] is False'
if printf '%s' '{"sessions": []}' | python3 "$ROOT/scripts/diagnose.py" >/dev/null
then exit 1
fi
out=$(printf '%s' '{"students":[{"name":"<b>A</b>","student_id":"=S1","attendance":"present","speak":1}]}' | python3 "$ROOT/scripts/diagnose.py")
printf '%s' "$out" | python3 -c 'import json,sys; x=json.load(sys.stdin); assert "<b>A</b>" in x["students"][0]["name"]; assert x["side_effects"]["notifications"] is False'
printf '%s\n' 'PASS=3 FAIL=0'
