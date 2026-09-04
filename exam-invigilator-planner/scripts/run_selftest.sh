#!/bin/sh
# 考场编排与监考调度生成器 - 自测脚本（30 条用例）
# 覆盖: 主流程 / 同义触发 / 组合调用 / 缺少输入 / 边界输入 / 异常数据 / XSS / 冲突约束
set -u
cd "$(dirname "$0")/.." || exit 1
PY="python3"
SCRIPT="scripts/exam_scheduler.py"
PASS=0; FAIL=0; FAILED_CASES=""
SELF_DIR="examples/selftest_cases"

run_case() {
    name="$1"; expect_ok="$2"; shift 2
    out=$("$PY" "$SCRIPT" "$@" 2>&1)
    rc=$?
    if [ "$expect_ok" = "ok" ]; then
        if [ "$rc" -eq 0 ]; then PASS=$((PASS+1)); echo "PASS $name";
        else FAIL=$((FAIL+1)); echo "FAIL $name (rc=$rc)"; echo "$out" | head -5; fi
    else
        # 期望有缺口/异常: rc=1 或输出包含 ⚠
        if echo "$out" | grep -q "⚠"; then PASS=$((PASS+1)); echo "PASS $name(expect-issue)";
        elif [ "$rc" -ne 0 ]; then PASS=$((PASS+1)); echo "PASS $name(rc=$rc)";
        else FAIL=$((FAIL+1)); echo "FAIL $name (expected issue, got ok)"; echo "$out" | head -5; fi
    fi
}

# ---- 1. 主流程 ----
run_case "主流程-完整期末编排" ok examples/sample_exam.json
run_case "主流程-输出JSON" ok examples/sample_exam.json --json
run_case "主流程-输出到文件" ok examples/sample_exam.json --out /tmp/exam_out.json

# stdin 管道（独立用例）
out=$(cat examples/sample_exam.json | "$PY" "$SCRIPT" --json 2>&1); rc=$?
if [ "$rc" -eq 0 ] && echo "$out" | grep -q '"plan"'; then PASS=$((PASS+1)); echo "PASS 主流程-stdin管道";
else FAIL=$((FAIL+1)); echo "FAIL stdin管道 (rc=$rc)"; echo "$out" | head -5; fi

# ---- 2. 同义触发（中文字段） ----
run_case "同义-中文考试字段" ok examples/selftest_cases/cn_fields.json
run_case "同义-中文日期2026年6月8日" ok examples/selftest_cases/cn_date.json
run_case "同义-单班级字符串" ok examples/selftest_cases/str_class.json

# ---- 3. 缺输入 ----
run_case "无考试场次" issue examples/selftest_cases/no_exams.json
run_case "无考场" issue examples/selftest_cases/no_rooms.json
run_case "无监考教师" issue examples/selftest_cases/no_invigilators.json
run_case "空对象" issue examples/selftest_cases/empty_obj.json
run_case "缺课程名" issue examples/selftest_cases/missing_course.json
run_case "缺名字监考" issue examples/selftest_cases/missing_teacher_name.json

# ---- 4. 边界输入 ----
run_case "常量大班(2000人)" ok examples/selftest_cases/big_class.json
run_case "教室不足" issue examples/selftest_cases/insufficient_rooms.json
run_case "教师不足" issue examples/selftest_cases/insufficient_teachers.json
run_case "容量单人数(1)" ok examples/selftest_cases/tiny_room.json
run_case "重复教师" ok examples/selftest_cases/dup_teacher.json
run_case "同日同时段重复考试" ok examples/selftest_cases/dup_exam.json

# ---- 5. 异常数据/约束 ----
run_case "教室容量负数" issue examples/selftest_cases/negative_capacity.json
run_case "日期非法" issue examples/selftest_cases/bad_date.json
run_case "牺牲未可用时段" issue examples/selftest_cases/unavailable_teacher.json
run_case "关于回避任课" ok examples/selftest_cases/avoid_own_class.json
run_case "XSS注入" ok examples/selftest_cases/xss_payload.json
run_case "超长字段" ok examples/selftest_cases/long_text.json
run_case "JSON损坏" issue examples/selftest_cases/broken.json
run_case "根节点非对象" issue examples/selftest_cases/root_array.json

# ---- 6. 组合调用 ----
run_case "组合-多场次多教室四天" ok examples/selftest_cases/multi_slot_full.json
run_case "组合-规则自定义45人/封顶3" ok examples/selftest_cases/multi_slot_full.json --json

echo "-------------------------------------"
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
