#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
PY="python3 $ROOT/scripts/audit_assessment.py"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
$PY --demo --out-dir "$TMP/demo" >/dev/null
test -s "$TMP/demo/review.json"
test -s "$TMP/demo/review.md"
$PY --input "$ROOT/examples/sample.json" --json > "$TMP/result.json"
python3 - "$TMP/result.json" <<'PY'
import json, sys
x=json.load(open(sys.argv[1]))
assert x['summary']['students'] == 3
assert x['summary']['remediation_candidates'] == 1
assert any('总评与上报值不一致' in s['flags'] for s in x['students'])
assert any('待补齐成绩' in s['flags'] for s in x['students'])
assert x['summary']['priority_counts']['P1'] == 2
assert all('priority' in s for s in x['students'])
PY
cat > "$TMP/bad.json" <<'JSON'
{"rules":{"weights":{"平时":0.5}},"students":[]}
JSON
if $PY --input "$TMP/bad.json" --strict >/dev/null 2>&1; then exit 1; fi
printf '%s\n' 'self-test passed: demo, normal, remediation, mismatch, missing input, strict error'
