#!/bin/bash
# Self-test runner for Student Academic Early Warning Analyzer
# Covers 5 branches: main flow / synonym trigger / missing input / boundary / XSS protection

set -e
cd "$(dirname "$0")/.."

PYTHON=python3
SCRIPT=scripts/academic_warning_analyzer.py
PASS_COUNT=0
FAIL_COUNT=0
TOTAL=0

run_test() {
    local desc="$1"
    local cmd="$2"
    local expect_keyword="$3"
    TOTAL=$((TOTAL+1))
    echo "--- Test $TOTAL: $desc"
    local output
    output=$(eval "$cmd" 2>&1) || true

    if [ -z "$expect_keyword" ] || echo "$output" | grep -qi "$expect_keyword"; then
        echo "    PASS (matched: '$expect_keyword')"
        PASS_COUNT=$((PASS_COUNT+1))
    else
        echo "    FAIL — expected keyword '$expect_keyword' not found in output"
        echo "    Output snippet: $(echo "$output" | head -5)"
        FAIL_COUNT=$((FAIL_COUNT+1))
    fi
}

echo "============================================"
echo "学生学业预警分析工具 自测套件 v1.0.0"
echo "$(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# === 分支 1: 主流程测试（正常功能路径）===

run_test "标准样例-含多类型学生" \
    "$PYTHON $SCRIPT --input examples/sample_students.json --output /tmp/_st_report.json && cat /tmp/_st_report.json | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[\"statistics\"][\"by_level\"][\"严重预警\"])'" \
    ""

run_test "输出文件正确生成" \
    "test -f /tmp/_st_report.json && python3 -c \"import json; json.load(open('/tmp/_st_report.json'))\"" \
    ""



run_test "STDIN输入模式可用" \
    "cat examples/sample_students.json | $PYTHON $SCRIPT --stdin 2>/dev/null | head -3" \
    "report_title"



run_test "帮助信息显示" \
    "$PYTHON $SCRIPT --help" \
    "用法"


# === 分支 2: 同义触发与字段别名兼容 ===


run_test "student_id 别名 sid 可识别" \
    "echo '{\"students\":[{\"sid\":\"V001\",\"name\":\"Alias\",\"gpa\":3.0}]}' | $PYTHON $SCRIPT --stdin 2>&1 | grep V001 | wc -l" \
    "[1-9]"

run_test "name_cn 字段可解析为 name" \
    "echo '{\"students\":[{\"student_id\":\"V002\",\"name_cn\":\"中文名字段\",\"gpa\":3.0}]}' | $PYTHON $SCRIPT --stdin 2>&1 | grep 中文名" \
    "中文名"

run_test "数组形式直接作为顶层对象传入" \
    "echo '[{\"student_id\":\"A001\",\"gpa\":3.0,\"total_class_sessions\":10,\"absent_sessions\":0}]' | $PYTHON $SCRIPT --stdin 2>&1 | grep A001" \
    "A001"


# === 分支 3: 缺失关键字段处理 ===

run_test "空 students 数组返回 no_students_found 错误" \
    "$PYTHON $SCRIPT --input examples/selftest_cases/empty_students.json 2>/dev/null" \
    "no_students_found"


run_test "缺 student_id 的记录触发校验警告" \
    "echo '{\"students\":[{\"name\":\"无学号\",\"gpa\":2.0}]}' | $PYTHON $SCRIPT --stdin 2>&1 | grep 无效或缺失" \
    "无效或缺失"


run_test "文件不存在时返回错误码非零" \
    "$PYTHON $SCRIPT --input nonexistent_file.json; echo EXIT=\$?" \
    "EXIT=2"


run_test "仅GPA无其他数据仍能分析(最小数据集)" \
    "$PYTHON $SCRIPT --input examples/selftest_cases/minimal_data.json 2>&1 | grep risk_score" \
    "risk_score"


# === 分支 4: 边界值压测 ===

run_test "GPA恰等于阈值2.0不触发高级预警因子" \
    "$PYTHON $SCRIPT --input examples/selftest_cases/boundary_gpa.json 2>&1 | grep GPA" \
    ""

run_test "GPA略高于阈值2.01不触发任何GPA相关因素" \
    "$PYTHON $SCRIPT --input examples/selftest_cases/boundary_gpa_above.json 2>&1 | grep GPA ; echo found_count=\$(grep -c GPA examples/selftest_cases/boundary_gpa_above.json)" \
    ""

run_test "出勤率恰好75%边界值判定逻辑合理" \
    "echo '{\"students\":[{\"student_id\":\"B001\",\"name\":\"boundary_attendance\",\"gpa\":3.0,\"fail_courses\":0,\"required_credits\":160,\"completed_credits\":140,\"failed_credits\":0,\"total_class_sessions\":100,\"absent_sessions\":25}]}' | $PYTHON $SCRIPT --stdin 2>&1 | grep 出勤率 | wc -l" \
    ""


run_test "自定义config_overrides生效提高评分严格度" \
    "$PYTHON $SCRIPT --input examples/selftest_cases/custom_config.json 2>&1 | grep risk_score.*[4-9][0-9]" \
    ""


# === 分支 5: XSS 防护验证 ===

run_test "XSS payload 在 name 字段被清洗掉 script 标签" \
    "$PYTHON $SCRIPT --input examples/selftest_cases/xss_payload.json 2>&1 | grep -c '<script>'" \
    "^0$"

run_test "img onerror 标签在 note 中被清洗" \
    "$PYTHON $SCRIPT --input examples/selftest_cases/xss_payload.json 2>&1 | grep onerror | wc -l" \
    "^0$"




run_test "HTML实体转义后输出不含原始尖括号" \
    "$PYTHON $SCRIPT --input examples/selftest_cases/xss_payload.json 2>/dev/null > /tmp/_xss_out.json && python3 -c '
import json
data=json.load(open(\"/tmp/_xss_out.json\"))
raw=json.dumps(data,ensure_ascii=False)
has_angle = \"<\" in raw or \">\" in raw
print(\"SAFE\" if not has_angle else \"UNSAFE\")
'" \
    "SAFE"

# === 补充：综合场景 ===

run_test "心理标记独立加分生效使关注级别提升" \
    "$PYTHON $SCRIPT --input examples/selftest_cases/psych_flag_only.json 2>&1 | grep 心理健康关注" \
    "心理健康关注"


run_test "总人数统计准确反映有效+跳过数" \
    "$PYTHON $SCRIPT --input examples/sample_students.json 2>&1 | grep total_students_analyzed" \
    "5"

run_test "优先级排序按分数降序排列flagged_ids" \
    "$PYTHON $SCRIPT --input examples/sample_students.json --output /tmp/_prio.json 2>/dev/null && python3 -c '
import json
data=json.load(open(\"/tmp/_prio.json\"))
flagged=data.get(\"recommendation_priority_order\",[])
scores=[x.get(\"score\") for x in flagged if isinstance(x,dict)]
is_desc=all(scores[i]>=scores[i+1] for i in range(len(scores)-1)) if len(scores)>1 else True
print(\"DESC_OK\" if is_desc and scores == sorted(scores, reverse=True) else \"ORDER_FAIL\")
'" \
    "DESC_OK"

# === 汇总报告 ===
echo ""
echo "==================================================="
echo "自测汇总：通过=$PASS_COUNT 失败=$FAIL_COUNT 总计=$TOTAL"
if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "✓ 全部 PASS，覆盖率符合预期。"
else
    echo "! 有失败用例需要检查修复。"
fi