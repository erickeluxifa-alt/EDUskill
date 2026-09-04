#!/bin/bash
# -*- coding: utf-8 -*-
# exam-followup-reviewer 自测脚本：~25 条断言，覆盖正常流程 / 边界 / 异常 / 安全。
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$HERE/scripts/followup_reviewer.py"
EX="$HERE/examples"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  ✗ $1"; }
check() { # check <描述> <命令...>
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then ok "$desc"; else bad "$desc"; fi
}
check_fail() { # check_fail <描述> <期望退出码> <命令...>
  local desc="$1" want="$2"; shift 2
  "$@" >/dev/null 2>&1
  local got=$?
  if [ "$got" = "$want" ]; then ok "$desc (退出码 $got)"; else bad "$desc (期望 $want 实得 $got)"; fi
}
assert_grep() { # assert_grep <描述> <文件> <模式>
  if grep -q "$3" "$2" 2>/dev/null; then ok "$1"; else bad "$1（未匹配 $3）"; fi
}
assert_nogrep() {
  if ! grep -q "$3" "$2" 2>/dev/null; then ok "$1"; else bad "$1（不应匹配 $3）"; fi
}

cd "$HERE"

echo "== 1. 正常流程：demo 双班横评 =="
rm -rf "$TMP/o1"; check "demo 运行成功(退出码0)" python3 "$SCRIPT" --demo --out-dir "$TMP/o1"
check "产出 7 个文件" test -f "$TMP/o1/followup_review.md"
[ -f "$TMP/o1/followup_report.html" ] && \
[ -f "$TMP/o1/class_compare.csv" ] && \
[ -f "$TMP/o1/kp_matrix.csv" ] && \
[ -f "$TMP/o1/help_list.csv" ] && \
[ -f "$TMP/o1/blueprint_feedback.json" ] && \
[ -f "$TMP/o1/followup_summary.json" ] && ok "产出 7 个文件" || bad "产出文件不全"
assert_grep "MD 含双班横评表" "$TMP/o1/followup_review.md" "计科2401"
assert_grep "MD 含共性薄弱归因" "$TMP/o1/followup_review.md" "共性薄弱"
assert_grep "回流 JSON 含难度建议" "$TMP/o1/blueprint_feedback.json" "下调难度\|控制难度\|可加码"
assert_grep "KPI 画像：良好/待提升" "$TMP/o1/followup_review.md" "良好"

echo "== 2. 单班 --analysis =="
rm -rf "$TMP/o2"
check "单班运行成功" python3 "$SCRIPT" --analysis "$EX/classA_analysis.json" --out-dir "$TMP/o2" --quiet
assert_grep "单班报告仅 1 个班级" "$TMP/o2/followup_review.md" "1 个"
assert_grep "单班帮扶清单渲染" "$TMP/o2/help_list.csv" "201114"
assert_grep "kp_matrix 含知识点" "$TMP/o2/kp_matrix.csv" "文件处理"

echo "== 3. 目录扫描 =="
mkdir -p "$TMP/o3/in/demo_output"
cp "$EX/classA_analysis.json" "$TMP/o3/in/classA_analysis.json"
cp "$EX/classB_analysis.json" "$TMP/o3/in/demo_output/classB_analysis.json"  # 应被跳过
check "目录扫描运行成功" python3 "$SCRIPT" --dir "$TMP/o3/in" --out-dir "$TMP/o3/out" --quiet
assert_grep "demo_output 被跳过（仅 1 班）" "$TMP/o3/out/followup_review.md" "1 个"
check_fail "目录不存在→退出码 2" 2 python3 "$SCRIPT" --dir "$TMP/o3/none" --out-dir "$TMP/o3/n" --quiet
mkdir -p "$TMP/empty_dir"
check_fail "目录无 analysis 文件→退出码 2" 2 python3 "$SCRIPT" --dir "$TMP/empty_dir" --out-dir "$TMP/o3/n2" --quiet

echo "== 4. 异常输入 =="
check_fail "文件不存在→退出码 2" 2 python3 "$SCRIPT" --analysis "$TMP/none.json" --out-dir "$TMP/o4a" --quiet
echo 'not json' > "$TMP/bad.json"
check_fail "非法 JSON→退出码 2" 2 python3 "$SCRIPT" --analysis "$TMP/bad.json" --out-dir "$TMP/o4b" --quiet
echo '{"a":1}' > "$TMP/nometa.json"
check_fail "缺 meta.questions→退出码 2" 2 python3 "$SCRIPT" --analysis "$TMP/nometa.json" --out-dir "$TMP/o4c" --quiet
check_fail "无任何输入→帮助退出码 2" 2 python3 "$SCRIPT" --out-dir "$TMP/o4d" --quiet

echo "== 5. 空学生/缺失数据容错 =="
python3 - "$EX/classA_analysis.json" "$TMP/empty_students.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
d["students"] = []
d["totals"]["n_present"] = 1
json.dump(d, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PY
rm -rf "$TMP/o5"; check "空学生明细仍可运行" python3 "$SCRIPT" --analysis "$TMP/empty_students.json" --out-dir "$TMP/o5" --quiet
assert_grep "空学生时给出提示" "$TMP/o5/followup_review.md" "未提供学生明细\|无学生"

echo "== 6. 安全：XSS 转义与公式注入 =="
python3 - "$EX/classA_analysis.json" "$TMP/xss.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
d["meta"]["exam"] = "期中<script>alert(1)</script>"
d["meta"]["class_name"] = "计科<img src=x onerror=alert(1)>"
for s in d["students"]:
    s["name"] = "=cmd|' /C calc'!A0"
json.dump(d, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PY
rm -rf "$TMP/o6"; check "含恶意文本可运行" python3 "$SCRIPT" --analysis "$TMP/xss.json" --out-dir "$TMP/o6" --quiet
assert_nogrep "HTML 不出现未转义 <script>" "$TMP/o6/followup_report.html" "<script>"
assert_nogrep "MD 不输出原样 <img" "$TMP/o6/followup_review.md" "<img"
assert_grep "CSV 公式注入加引号前缀" "$TMP/o6/help_list.csv" "'=cmd"
assert_nogrep "CSV 不得裸公式" "$TMP/o6/help_list.csv" "=cmd\+1"

echo "== 7. 确定性：两次运行结果一致 =="
python3 "$SCRIPT" --demo --out-dir "$TMP/do1" --quiet
python3 "$SCRIPT" --demo --out-dir "$TMP/do2" --quiet
if diff -q "$TMP/do1/followup_summary.json" "$TMP/do2/followup_summary.json" >/dev/null; then
  ok "确定性输出（hash 一致）"
else
  bad "确定性输出（两次结果不一致）"
fi

echo "== 8. 参数开关 =="
rm -rf "$TMP/o8"; check "--no-html 不产 html" python3 "$SCRIPT" --demo --out-dir "$TMP/o8" --quiet --no-html && [ ! -f "$TMP/o8/followup_report.html" ] && ok "--no-html 生效" || bad "--no-html 未生效"
rm -rf "$TMP/o8b"; check "--no-md 不产 md" python3 "$SCRIPT" --demo --out-dir "$TMP/o8b" --quiet --no-md && [ ! -f "$TMP/o8b/followup_review.md" ] && ok "--no-md 生效" || bad "--no-md 未生效"

echo ""
echo "结果: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = "0" ]