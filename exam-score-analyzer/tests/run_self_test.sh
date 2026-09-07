#!/usr/bin/env bash
# 自测脚本：覆盖常规/同义触发/边界输入/异常数据/安全/组合交互
# 用法: bash run_self_test.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="python3"
S="$ROOT/scripts/score_analyzer.py"
T="$ROOT/tests/tmp"
MX="$ROOT/examples/sample_exam_meta.json"
SC="$ROOT/examples/sample_scores.csv"
SCN="$T/s_normal.csv"
PASS=0; FAIL=0
rm -rf "$T"; mkdir -p "$T"

# 生成夹具
$PY "$ROOT/tests/make_fixtures.py" "$T" >/dev/null || { echo "夹具生成失败"; exit 1; }

run_case() { # id 期望退出码 描述 命令...
  local id="$1" exp="$2" desc="$3"; shift 3
  "$@" >/dev/null 2>"$T/err.txt"
  local rc=$?
  if [ "$rc" = "$exp" ]; then
    echo "[PASS] $id - $desc"
    PASS=$((PASS+1))
  else
    echo "[FAIL] $id - $desc (期望 $exp, 实际 $rc)"
    sed 's/^/        /' "$T/err.txt" | head -3
    FAIL=$((FAIL+1))
  fi
}

check_marker() { # id 文件 关键词
  if grep -q "$3" "$2" 2>/dev/null; then
    echo "[PASS] $1 - 内容: $3"
    PASS=$((PASS+1))
  else
    echo "[FAIL] $1 - 未找到「$3」(文件 $2)"
    FAIL=$((FAIL+1))
  fi
}

# ---------- 常规流程 ----------
run_case  01 0 "demo 全流程" $PY $S --demo --out-dir "$T/o01"
check_marker "01b" "$T/o01/analysis_report.md" "成绩分析报告"
run_case  02 0 "示例 Meta+CSV 常规分析" $PY $S --meta "$MX" --scores "$SC" --out-dir "$T/o02"
check_marker "02b" "$T/o02/analysis_report.md" "分数段分布"
run_case  03 0 "中文表头(姓名/学号/班级)" $PY $S --meta "$MX" --scores "$T/csv_cn.csv" --out-dir "$T/o03"
check_marker "03b" "$T/o03/analysis_report.md" "及格率"

# ---------- 确定性 ----------
run_case  04 0 "同一输入跑两次" $PY $S --meta "$MX" --scores "$SCN" --out-dir "$T/o04a"
run_case  04b 0 "同一输入跑第二次" $PY $S --meta "$MX" --scores "$SCN" --out-dir "$T/o04b"
if cmp -s "$T/o04a/analysis.json" "$T/o04b/analysis.json"; then
  echo "[PASS] 04c - 输出确定性（两次 JSON 一致）"; PASS=$((PASS+1))
else
  echo "[FAIL] 04c - 两次输出不一致（非确定性）"; FAIL=$((FAIL+1))
fi

# ---------- 缺考 / 未作答 ----------
run_case  05 0 "缺考+未作答学生样本" $PY $S --meta "$MX" --scores "$SC" --out-dir "$T/o05"
check_marker "05b" "$T/o05/analysis_report.md" "缺考"
check_marker "05c" "$T/o05/analysis_report.md" "未作答"

# ---------- 边界输入 ----------
run_case  06 2 "meta 文件不存在" $PY $S --meta "$T/none.json" --scores "$SC" --out-dir "$T/x"
run_case  07 2 "scores 文件不存在" $PY $S --meta "$MX" --scores "$T/none.csv" --out-dir "$T/x"
run_case  08 2 "CSV 表头为空" $PY $S --meta "$MX" --scores "$T/empty_header.csv" --out-dir "$T/x"
run_case  09 2 "题分合计!=total_marks" $PY $S --meta "$T/mismatch_meta.json" --scores "$SCN" --out-dir "$T/x"
run_case  10 2 "meta.questions 为空" $PY $S --meta "$T/empty_q_meta.json" --scores "$SCN" --out-dir "$T/x"
run_case  11 2 "meta 非法 JSON" $PY $S --meta "$T/bad_json.json" --scores "$SCN" --out-dir "$T/x"
run_case  12 2 "--pass-rate=1.2 越界" $PY $S --meta "$MX" --scores "$SCN" --out-dir "$T/x" --pass-rate 1.2
run_case  13 2 "全员缺考(无有效学生)" $PY $S --meta "$MX" --scores "$T/all_absent.csv" --out-dir "$T/x"
run_case  14 0 "单名学生(降级缺 sd/区分度)" $PY $S --meta "$MX" --scores "$T/one_student.csv" --out-dir "$T/o14"
run_case  15 0 "全满分班(区分度 0/alpha 无数据)" $PY $S --meta "$MX" --scores "$T/all_full.csv" --out-dir "$T/o15"
run_case  16 0 "bins=0 自动兜底" $PY $S --meta "$MX" --scores "$SCN" --out-dir "$T/o16" --bins 0

# ---------- 列名同义兼容 ----------
run_case  17 0 "题列 t1..t8" $PY $S --meta "$MX" --scores "$T/csv_t.csv" --out-dir "$T/o17"
run_case  18 0 "题列 题目1..题目8" $PY $S --meta "$MX" --scores "$T/csv_cnq.csv" --out-dir "$T/o18"

# ---------- 异常单元格 ----------
run_case  19 0 "非数字单元格→缺失+告警" $PY $S --meta "$MX" --scores "$T/bad_cell.csv" --out-dir "$T/o19"
check_marker "19b" "$T/o19/analysis_report.md" "未作答"
run_case  20 0 "得分超题分→按缺失处理" $PY $S --meta "$MX" --scores "$T/over_cell.csv" --out-dir "$T/o20"
run_case  21 2 "--strict 见告警即失败" $PY $S --meta "$MX" --scores "$T/bad_cell.csv" --out-dir "$T/o21" --strict

# ---------- 输出与安全 ----------
run_case  22 0 "--no-html 不生成 html" $PY $S --meta "$MX" --scores "$SCN" --out-dir "$T/o22" --no-html
if [ -f "$T/o22/report.html" ]; then echo "[FAIL] 22b - 不应生成 report.html"; FAIL=$((FAIL+1)); else echo "[PASS] 22b - 未生成 report.html"; PASS=$((PASS+1)); fi
run_case  23 0 "XSS 名称输入可分析" $PY $S --meta "$T/meta_xss.json" --scores "$T/csv_xss.csv" --out-dir "$T/o23"
if grep -q "<script>" "$T/o23/report.html"; then echo "[FAIL] 23b - HTML 含原始 script"; FAIL=$((FAIL+1)); else echo "[PASS] 23b - HTML 无原始 script"; PASS=$((PASS+1)); fi
if grep -q "&lt;script&gt;" "$T/o23/report.html"; then echo "[PASS] 23c - 文本已转义"; PASS=$((PASS+1)); else echo "[FAIL] 23c - 未转义"; FAIL=$((FAIL+1)); fi
run_case  24 0 "公式注入名(=SUM)可分析" $PY $S --meta "$MX" --scores "$T/csv_formula.csv" --out-dir "$T/o24"
if grep -q "'=SUM(A1)" "$T/o24/students.csv"; then echo "[PASS] 24b - CSV 首字符加 ' 防注入"; PASS=$((PASS+1)); else echo "[FAIL] 24b - 未见防注入前缀"; FAIL=$((FAIL+1)); fi

# ---------- 组合交互 ----------
run_case  25 0 "组合:中文列名+bins5+自定义目录" $PY $S --meta "$MX" --scores "$T/csv_cn.csv" --out-dir "$T/o25" --bins 5
check_marker "25b" "$T/o25/analysis_report.md" "5 段"
run_case  26 0 "自定义及格/优秀线" $PY $S --meta "$MX" --scores "$SCN" --out-dir "$T/o26" --pass-rate 0.5 --excellent-rate 0.8
run_case  27 0 "--version" $PY $S --version
run_case  28 0 "--help" $PY $S --help
run_case  29 0 "analysis.json 结构化产物" $PY $S --meta "$MX" --scores "$SCN" --out-dir "$T/o29"
check_marker "29b" "$T/o29/analysis.json" "teaching"
run_case  30 0 "class_summary.csv 产物" $PY $S --meta "$MX" --scores "$SCN" --out-dir "$T/o30"
check_marker "30b" "$T/o30/class_summary.csv" "及格率"

echo "=========================================="
echo "自测统计: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] && echo "ALL PASSED" || echo "HAS FAILURES"
exit $FAIL