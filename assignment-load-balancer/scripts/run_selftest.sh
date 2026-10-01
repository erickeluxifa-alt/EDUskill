#!/usr/bin/env bash
set -u
BASE="$(cd "$(dirname "$0")/.." && pwd)"
PY="python3 $BASE/scripts/assignment_analyze.py"
PASS=0
FAIL=0
run_case() {
  local name="$1" file="$2" pattern="$3"; shift 3
  local out rc
  out=$(eval "$PY '$BASE/examples/$file' $*" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q "$pattern"; then
    printf 'PASS %s\n' "$name"; PASS=$((PASS+1))
  else
    printf 'FAIL %s\n%s\n' "$name" "$out"; FAIL=$((FAIL+1))
  fi
}
run_error_case() {
  local name="$1" file="$2" pattern="$3"
  local out rc
  out=$(eval "$PY '$BASE/examples/$file'" 2>&1); rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "$pattern"; then
    printf 'PASS %s\n' "$name"; PASS=$((PASS+1))
  else
    printf 'FAIL %s\n%s\n' "$name" "$out"; FAIL=$((FAIL+1))
  fi
}
run_case T01_main sample_assignments.json '发现问题：3 条'
run_case T02_json sample_assignments.json '"conflicts"' --json
run_case T03_no_conflict no_conflict.json '未发现截止日期密集'
run_case T04_root_array no_conflict.json '有效记录：2 条'
run_case T05_capacity sample_assignments.json '周负荷超载' --capacity 5
run_case T06_window sample_assignments.json '截止日期密集' --window 1
run_case T07_suggestions sample_assignments.json '延期建议'
run_case T08_missing_field missing.json '无效记录：1 条'
run_case T09_bad_date bad_date.json '无效记录：1 条'
run_case T10_non_object non_object.json '无效记录：1 条'
run_case T11_empty empty.json '有效记录：0 条'
run_case T12_xss xss.json '&lt;script&gt;'
run_case T13_long_text long.json '...(truncated)'
run_case T14_single_day single.json '有效记录：1 条'
run_case T15_zero_hours zero.json '有效记录：1 条'
run_case T16_priority sample_assignments.json '移至 2026-08-29'
run_error_case T17_invalid_json invalid.json '无法读取有效 JSON'
run_error_case T18_bad_root bad_root.json 'JSON 根节点必须是数组'
run_case T19_capacity_zero sample_assignments.json '周负荷超载' --capacity 0
run_case T20_help sample_assignments.json 'usage:' --help
printf '\n结果：%d/20 PASS，%d FAIL\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
