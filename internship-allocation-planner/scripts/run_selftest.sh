#!/bin/bash
# internship_allocator 自测脚本
# 用法: bash scripts/run_selftest.sh
# 用例清单格式: <文件>|<期望退出码>|<必须包含>|<不得包含>|<count:文本=期望次数>
# 退出码: 0=无缺口冲突被分配完成 | 1=存在缺口/冲突 | 2=输入/IO 错误
cd "$(dirname "$0")/.." || exit 2
PY=python3
SCRIPT=$(pwd)/scripts/internship_allocator.py
CASES=$(pwd)/examples/selftest_cases
PASS=0; FAIL=0; FAILED_CASES=()

chek() {
  local name="$1" exp="$2" con="$3" ncon="$4" cnt="$5" args="$6"
  local out ec
  out=$( "$PY" "$SCRIPT" "$CASES/$name" $args 2>&1 ); ec=$?
  local ok=1 detail=""
  if [ "$ec" != "$exp" ]; then ok=0; detail+="exit=$ec(期望$exp) "; fi
  if [ -n "$con" ] && ! printf '%s' "$out" | grep -Fq "$con"; then ok=0; detail+="缺包含[$con] "; fi
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
  while IFS='|' read -r f ex con ncon cnt args; do
    [ -z "$f" ] && continue
    chek "$f" "$ex" "$con" "$ncon" "$cnt" "$args"
  done
} <<'EOF'
alloc_basic_ok.json|0|整体分配率 100%|||
alloc_second_choice.json|0|二志愿|||
alloc_gap.json|1|志愿全满|||
alloc_fallback.json|0|调剂|||
alloc_major_strict.json|1|专业不符|||
alloc_chinese_only.json|0|整体分配率 100%|||
no_students.json|2|缺少必要字段|||
no_units.json|2|缺少必要字段：units/单位 列表|||
default_cap.json|0|整体分配率 100%|||
fill_one_one.json|0|整体分配率 100%|||
zero_capacity.json|1|志愿全满|||
pressure_20.json|0|整体分配率 100%|||
window_gap.json|1|时段无交集|||
negative_capacity.json|2|不能为负数|||
bad_vocation_ref.json|1|志愿单位不存在|||
dup_names.json|0|整体分配率 100%|||
bad_json.bad.json|2|解析失败|||
students_not_list.json|2|必须是数组|||
check_overflow.json|1|单位期次数超额|||--check
check_unknown_unit.json|1|未知单位|||--check
check_unknown_window.json|1|未知期次|||--check
check_multi_unit.json|1|学生分属多单位|||--check
check_clean.json|0|检查通过|||--check
xss.json|0|&lt;script&gt;|<script>
EOF

# 样例主流程（用例 #25：中英别名混合 + 期次窗口 + 利用率统计）
out=$( "$PY" "$SCRIPT" examples/sample_alloc.json 2>&1 ); ec=$?
if [ "$ec" = "0" ] && printf '%s' "$out" | grep -Fq "整体分配率 100%" && printf '%s' "$out" | grep -Fq "一志愿命中：5/6"; then
  echo "PASS sample_alloc_main"; PASS=$((PASS+1))
else
  echo "FAIL sample_alloc_main exit=$ec"; FAIL=$((FAIL+1)); FAILED_CASES+=("sample_alloc_main: exit=$ec")
fi

# 样例体检模式（用例 #26：sample_check.json 超额+未知单位+多单位）
out=$(cd "$(dirname "$0")/.." && "$PY" "$SCRIPT" examples/sample_check.json --check 2>&1); ec=$?
if [ "$ec" = "1" ] && printf '%s' "$out" | grep -Fq "单位期次数超额" && printf '%s' "$out" | grep -Fq "未知单位" && printf '%s' "$out" | grep -Fq "学生分属多单位"; then
  echo "PASS sample_check_combo"; PASS=$((PASS+1))
else
  echo "FAIL sample_check_combo exit=$ec"; FAIL=$((FAIL+1)); FAILED_CASES+=("sample_check_combo: exit=$ec")
fi

# 副作用用例 #27-29：--out 覆盖保护与 --force
TMP=$(mktemp -d)
printf '{"students":[{"name":"甲","options":["A单位"]}],"units":[{"name":"A单位","capacity":1}]}' > "$TMP/t.json"
out=$("$PY" "$SCRIPT" "$TMP/t.json" --json --out "$TMP/out.json" 2>&1); ec=$?
if [ "$ec" = "0" ] && [ -f "$TMP/out.json" ]; then echo "PASS out_write_first"; PASS=$((PASS+1)); else
  echo "FAIL out_write_first ec=$ec"; FAIL=$((FAIL+1)); FAILED_CASES+=("out_write_first: ec=$ec")
fi
out=$("$PY" "$SCRIPT" "$TMP/t.json" --json --out "$TMP/out.json" 2>&1); ec=$?
if [ "$ec" = "2" ] && printf '%s' "$out" | grep -Fq "已存在"; then echo "PASS out_exists_reject"; PASS=$((PASS+1)); else
  echo "FAIL out_exists_reject ec=$ec"; FAIL=$((FAIL+1)); FAILED_CASES+=("out_exists_reject: ec=$ec")
fi
out=$("$PY" "$SCRIPT" "$TMP/t.json" --json --out "$TMP/out.json" --force 2>&1); ec=$?
if [ "$ec" = "0" ] && "$PY" -c "import json,sys;json.load(open('$TMP/out.json'))" 2>/dev/null; then echo "PASS out_force_overwrite"; PASS=$((PASS+1)); else
  echo "FAIL out_force_overwrite ec=$ec"; FAIL=$((FAIL+1)); FAILED_CASES+=("out_force_overwrite: ec=$ec")
fi
rm -rf "$TMP"

echo "----------------------------------------"
echo "PASS=$PASS FAIL=$FAIL"
for c in "${FAILED_CASES[@]}"; do echo "  FAIL -> $c"; done
[ "$FAIL" -eq 0 ] || exit 1