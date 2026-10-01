#!/usr/bin/env bash
set -u
BASE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SCRIPT="$BASE/scripts/radar.py"
SAMPLE="$BASE/examples/sample_milestones.json"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
pass=0
run(){ name="$1"; shift; if "$@" >"$TMP/out" 2>"$TMP/err"; then printf 'PASS %s\n' "$name"; pass=$((pass+1)); else printf 'FAIL %s\n' "$name"; cat "$TMP/err"; exit 1; fi; }
run "syntax" python3 -m py_compile "$SCRIPT"
run "default report" python3 "$SCRIPT" "$SAMPLE" --as-of 2026-08-30
run "json report" python3 "$SCRIPT" "$SAMPLE" --as-of 2026-08-30 --json
python3 "$SCRIPT" "$SAMPLE" --as-of 2026-08-30 --json >"$TMP/report.json"
python3 - "$TMP/report.json" <<'PY'
import json, sys
r=json.load(open(sys.argv[1]))
assert r['summary']['high'] >= 1
assert any(x['id']=='M-002' for x in r['risks'])
assert any(x['dimension']=='project' for x in r['congestion'])
assert any(x['dimension']=='owner' for x in r['congestion'])
PY
printf 'PASS JSON assertions\n'; pass=$((pass+1))
run "preview confirmation" python3 "$SCRIPT" "$SAMPLE" --as-of 2026-08-30 --json --preview
python3 - "$TMP/out" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
assert r['preview']['requires_confirmation'] is True
assert r['preview']['actions']
PY
printf 'PASS preview assertions\n'; pass=$((pass+1))
cat >"$TMP/bad.json" <<'JSON'
{"milestones":[{"id":"x","project":"p","milestone":"m","owner":"o","due_date":"2026-99-01","status":"in_progress"}]}
JSON
run "invalid date reported" python3 "$SCRIPT" "$TMP/bad.json" --as-of 2026-08-30 --json
python3 - "$TMP/out" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
assert r['validation']['valid'] == 0
assert r['validation']['errors']
PY
printf 'PASS invalid date assertions\n'; pass=$((pass+1))
cat >"$TMP/missing.json" <<'JSON'
{"milestones":[{"id":"x","project":"p","milestone":"m","owner":"o","due_date":"2026-09-01","status":"in_progress"}]}
JSON
run "missing progress tolerated" python3 "$SCRIPT" "$TMP/missing.json" --as-of 2026-08-30 --json
printf '自测通过：%s 项\n' "$pass"
