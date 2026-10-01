#!/bin/bash
# lab_reservation_scheduler 自测脚本
# 用法: bash scripts/run_selftest.sh
# 用例清单: <文件>|<期望退出码>|<必须包含>|<不得包含>|<count:文本=期望次数>
cd "$(dirname "$0")/.." || exit 2
PY=python3
SCRIPT=$(pwd)/scripts/lab_reservation_scheduler.py
CASES=$(pwd)/examples/selftest_cases
PASS=0; FAIL=0; FAILED_CASES=()

chek() {
  local name="$1" exp="$2" con="$3" ncon="$4" cnt="$5"
  local out; out=$( "$PY" "$SCRIPT" "$CASES/$name" 2>&1 ); local ec=$?
  local ok=1 detail=""
  if [ "$ec" != "$exp" ]; then ok=0; detail+="exit=$ec(期望$exp) "; fi
  if [ -n "$con" ] && ! printf '%s' "$out" | grep -Fq "$con" ; then ok=0; detail+="缺包含[$con] "; fi
  if [ -n "$ncon" ] && printf '%s' "$out" | grep -Fq "$ncon"; then ok=0; detail+="出现禁用[$ncon] "; fi
  if [ -n "$cnt" ]; then
    local pat=${cnt%%:*}; local nn=${cnt##*:}
    local n; n=$(printf '%s' "$out" | grep -Fo "$pat" | wc -l | tr -d ' ')
    if [ "$n" -ne "$nn" ]; then ok=0; detail+="count=$n(期望$nn)[$pat] "; fi
  fi
  if [ $ok -eq 1 ]; then echo "PASS ${name%.json}"; PASS=$((PASS+1)); else
    echo "FAIL ${name%.json}  $detail"; FAIL=$((FAIL+1)); FAILED_CASES+=("$name: $detail")
  fi
}

{
  while IFS='|' read -r f ex con ncon cnt; do
    [ -z "$f" ] && continue
    chek "$f" "$ex" "$con" "$ncon" "$cnt"
  done
} <<'EOF'
resolved_ok.json|0|全部解决 3||
synonyms.json|0|全部解决 2||
date_formats.json|0|全部解决 3||
slot_alias.json|0|全部解决 3||
teacher_conflict_off.json|0|||张伟:3
teacher_conflict_on.json|1|缺口||
empty_input.json|2|缺少 resources||
no_requests.json|2|没有可排的预约申请||
missing_date.json|2|日期缺失||
missing_students.json|2|人数缺失||
missing_resources.json|2|没有可用实验室资源||
bad_resources.json|2|不是对象||
exact_capacity.json|0|全部解决 1||
split_two_labs.json|0|全部解决 1||
split_disabled.json|1|缺口||
big_class.json|0|全部解决 1||
huge_class.json|1|缺口 1350||
zero_students.json|2|人数缺失或非法||
negative_students.json|2|人数缺失或非法||
empty_resources.json|2|为空列表||
closed_date.json|1|缺口||
missing_equipment.json|1|缺口||
no_matching_type.json|1|缺口||
bad.json.json|2|解析失败||
requests_not_list.json|2|必须为列表||
custom_slots.json|0|15:00-17:00||
priority_first.json|0|高优先课||
xss.json|0|&lt;script&gt;|<script>
EOF

# 样例主流程（用例 #28：组合：中英别名+日期形态+已排定+跨槽拆分+缺口）
out=$( "$PY" "$SCRIPT" examples/sample_lab.json 2>&1 ); ec=$?
if [ "$ec" = "1" ] && printf '%s' "$out" | grep -Fq "缺口 5" && printf '%s' "$out" | grep -Fq "数控加工基础实验"; then
  echo "PASS sample_main_combo"; PASS=$((PASS+1))
else
  echo "FAIL sample_main_combo"; FAIL=$((FAIL+1)); FAILED_CASES+=("sample_main_combo: exit=$ec")
fi

echo "----------------------------------------"
echo "PASS=$PASS FAIL=$FAIL"
for c in "${FAILED_CASES[@]}"; do echo "  FAIL -> $c"; done
[ "$FAIL" -eq 0 ] || exit 1