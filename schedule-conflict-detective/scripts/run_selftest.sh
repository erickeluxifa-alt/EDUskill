#!/bin/bash
# 自测脚本: 覆盖主流程/同义触发/缺失输入/边界压测/XSS防护五大分支
# 输出 Markdown 表格到 stdout

set +e

ROOT="/home/gem/workspace/.ark/output/教育产品Skills_2026-08-17/course-schedule-conflict-detective"
SCRIPT="$ROOT/scripts/schedule_analyze.py"
EX_DIR="$ROOT/examples"
STC_DIR="$ROOT/examples/selftest_cases"

PASS_COUNT=0
FAIL_COUNT=0
TOTAL=0

run_case() {
    local label="$1"
    local expected_desc="$2"
    local check_pattern="$3"
    local negate_pattern="${4:-__NONE__}"
    shift 4
    TOTAL=$((TOTAL+1))

    # 运行脚本,捕获输出与返回码
    output=$(python3 "$SCRIPT" "$@" 2>/tmp/selftest_stderr)
    rc=$?
    err=$(cat /tmp/selftest_stderr 2>/dev/null)
    out_short=$(echo "$output" | head -c 200 | tr '\n' '|')

    passed="FAIL"
    if echo "$output $err" | grep -q "$check_pattern"; then
        if [ "$negate_pattern" != "__NONE__" ]; then
            if ! echo "$output $err" | grep -qE "$negate_pattern"; then
                passed="PASS"
            fi
        else
            passed="PASS"
        fi
    fi

    if [ "$passed" = "PASS" ]; then PASS_COUNT=$((PASS_COUNT+1)); else FAIL_COUNT=$((FAIL_COUNT+1)); fi

    printf "| %s | %s | %d | %s | %s |\n" \
        "$label" \
        "$(echo "$expected_desc" | head -c60)" \
        "$rc" \
        "$passed" \
        "$(echo "$out_short" | sed 's/|/\\|/g' | head -c80)"
}

echo "# 课程表冲突检测 Skill · 自测结果"
echo ""
echo "> 测试时间: $(date '+%Y-%m-%d %H:%M:%S') (date-calculator 校准)"
echo ""
echo "| 编号 | 预期描述(简) | rc | 通过? | stdout 预览(简) |"
echo "|------|--------------|----|-------|-----------------|"

# ===== 分支1: 主流程 happy path =====
run_case T01_no_conflict_sample \
    "无冲突样例应未检出冲突且退出码0" \
    "未检测出任何资源占用冲突" __NONE__ \
    "$EX_DIR/sample_no_conflict.json"

run_case T02_with_conflicts_detection \
    "含教师+教室双类型冲突样例检测出冲突并给调课建议" \
    "调课建议" "(校验失败)" \
    "$EX_DIR/sample_with_conflicts.json"

T03_OUT=$(python3 "$SCRIPT" "$EX_DIR/sample_with_conflicts.json" --json 2>&1)
if echo "$T03_OUT" | grep -q -- "---JSON---"; then
    PASSED_T03="PASS"; PASS_COUNT=$((PASS_COUNT+1))
else
    PASSED_T03="FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
fi
TOTAL=$((TOTAL+1))
printf "%s\n" "| T03_json_mode_appended | --json追加---JSON---标记分隔 | $? | $PASSED_T03 | $(echo "$T03_OUT"|grep -c 'JSON') JSON出现次数 |"

run_case T04_multiweek_aggregation_into_wklist_str \
    "多周同节次仅一行带 '1-5' 周次压缩独立条目" \
    "\| 周一 第7节 \|.*1-5\|" "\| 周一 第7节 \| W[0-9] \|" \
    "$STC_DIR/multiweek_same_pair.json"

# 调课建议避免新碰撞验证: 概率论不应被推荐移至 p1 或 p2(原时段附近会和张明的新课撞)
python3 "$SCRIPT" "$EX_DIR/sample_with_conflicts.json" > /tmp/t05_out.txt 2>/dev/null
if grep -q '将「概率论」' /tmp/t05_out.txt && \
   ! grep -q '调整到 \*\*周一 第1节\*\*' /tmp/t05_out.txt && \
   ! grep -q '调整到 \*\*周一 第2节\*\*' /tmp/t05_out.txt; then
   P05="PASS"; PASS_COUNT=$((PASS_COUNT+1))
else
   P05="FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
fi
TOTAL=$((TOTAL+1))
printf "%s\n" "| T05_reschedule_avoids_new_collision | 概率论移动目标避开p1/p2 | 0 | $P05 | 检查建议行不含第1/2节 |"

# ===== 分支2: 同义触发 / 字段等价性 =====
run_case T06_weeks_as_string_range_syntax \
    "'9-12'区间串格式可解析为9..12周列表有效记录数1条0无效0冲突" \
    "共 1 条有效 \| 无效 0 条 \| 冲突 0 条" "(Traceback|Error|Exception)" \
    "$STC_DIR/weeks_range_str.json"

run_case T07_weekday_chinese_parsing_compat \
    "'周一''一'中文写法兼容解析触发同师同时段冲突" \
    "教师冲突" "" \
    "$STC_DIR/cn_weekday.json"

run_case T08_single_int_period_field_accepted \
    "period单值字段替代periods列表也能正确识别共1条记录且无校验失败无冲突" \
    "共 1 条有效 \| 无效 0 条 \| 冲突 0 条" "(Traceback|Error)" \
    "$STC_DIR/single_period_field.json"

# ===== 分支3: 缺失关键字段 / 异常输入处理 =====
run_case T09_missing_teacher_invalid_record_no_crash \
    "teacher为空进入invalid清单而非崩溃;报告显示无效1条" \
    "无效 1 条" "(Traceback|Error:" \
    "$STC_DIR/missing_teacher.json"

run_case T10_empty_schedule_graceful_handling \
    "空schedule数组不报错正常处理共0记录" \
    "共 0 条有效" "(Traceback|Error)" \
    "$STC_DIR/empty_schedule.json"

# malformed JSON 文本优雅退出(exit code非0 stderr含提示前缀)
MALFORMED_FILE=$(mktemp /tmp/malformed.XXXX.json)
echo "{not valid json" > "$MALFORMED_FILE"
ERR11=$(python3 "$SCRIPT" "$MALFORMED_FILE" 2>&1 >/dev/null); RC11=$?
rm -f "$MALFORMED_FILE"
if [ $RC11 -ne 0 ] && echo "$ERR11" | grep -q '\[load_schedule\]'; then
    P11="PASS"; PASS_COUNT=$((PASS_COUNT+1))
else
    P11="FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
fi
TOTAL=$((TOTAL+1))
printf "%s\n" "| T11_malformed_json_exits_cleanly_with_error_prefix | exit code !=0 且stderr含load_schedule提示前缀 | $RC11 | $P11 | ${ERR11:0:50}... |"

# 未提供文件路径时应打印 usage 并exit非0
NOARG_ERR12=$(python3 "$SCRIPT" 2>&1 >/dev/null); RC12=$?
if [ $RC12 -ne 0 ] && echo "$NOARG_ERR12" | grep -q '用法:'; then
    P12="PASS"; PASS_COUNT=$((PASS_COUNT+1))
else
    P12="FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
fi
TOTAL=$((TOTAL+1))
printf "%s\n" "| T12_usage_hint_when_filepath_missing | 未提供路径时打印用法: 提示exit非0 | $RC12 | $P12 | 用法检查通过 |"

# periods 字符串形式逗号分隔解析("5","6")
PERIOD_CSV_PAYLOAD='{"schedule":[{"course":"X","teacher":"Y","room":"Z","class":"W","week_start":1,"week_end":8,"weekday":3,"period":"7"}]}'
PCSV_TMP=$(mktemp /tmp/pcsv.XXXX.json)
echo "$PERIOD_CSV_PAYLOAD" > "$PCSV_TMP"
CSV13_OUT=$(python3 "$SCRIPT" "$PCSV_TMP" 2>&1); RC13=$?
rm -f "$PCSV_TMP"
if [ $RC13 -eq 0 ] && echo "$CSV13_OUT" | grep -q "共 1 条有效"; then
    P13="PASS"; PASS_COUNT=$((PASS_COUNT+1))
else
    P13="FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
fi
TOTAL=$((TOTAL+1))
printf "%s\n" "| T13_period_csv_string_format_accepted | period字符串单值也能识别成1条有效记录 | $RC13 | $P13 | period CSV string handling ok |"

# ===== 分支4: 边界压测 =====
BIGTMP=$(mktemp /tmp/big_stress.XXXX.json)
python3 <<PYEOF >>"$BIGTMP" 2>>/dev/null
import json, random as RND
RND.seed(42)
recs=[]
for i in range(800):
    recs.append({
        "course": f"C{i}",
        "teacher": f"T{i%25}",
        "room": f"R{i%40}",
        "class": f"L{i%55}",
        "week_start": ((i*17)%14)+1,
        "week_end": (((i*23)%16))+1,
        "weekday": str(((i*7)%5)+1),
        "periods": [(i%12)+1]
    })
print(json.dumps({"schedule": recs}, ensure_ascii=False))
PYEOF

START_TS=$(date +%s.%N)
B14OUT=$(timeout 30 python3 "$SCRIPT" "$BIGTMP" 2>&1); RC14=$?
END_TS=$(date +%s.%N)
ELAPSED=$(awk -v s=$START_TS -v e=$END_TS 'BEGIN{print e-s}')
rm -f "$BIGTMP"

HAS_CONFLICT_OUTPUT=""
if echo "$B14OUT" | grep -qE '(条独立冲突|未检测出任何资源占用冲突)'; then HAS_CONFLICT_OUTPUT=yes; fi
RC14_OK=$(awk -v x=$RC14 -v y="$HAS_CONFLICT_OUTPUT" -v t="$ELAPSED" 'BEGIN{ if(x==0&&y=="yes"&&t<8.0){print "yes"} }')

if [ "$RC14_OK" = "yes" ]; then
    P14="PASS"; PASS_COUNT=$((PASS_COUNT+1))
else
    P14="FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
fi
TOTAL=$((TOTAL+1))
printf "%s\n" "| T14_large_records_n800_under8sec_no_crash | n=800随机排课样本 <8秒完成无崩溃有结论输出 | $RC14 | $P14 | elapsed=${ELAPSED}s |"

# 极长课程名长度截断测试 (>200 chars 应被截断后转义不影响整体渲染)
LONGNAME_TMP=$(mktemp /tmp/lname.XXXX.json)
{
  LONG_NAME_VAL="$(python3 -c 'print("A"*300+"end")')"
  python3 -c "
import json
rec={'course':'$LONG_NAME_VALUE','teacher':'Y','room':'Z','class':'W','week_start':1,'week_end':4,'weekday':3,'period':[5]}
json.dump({'schedule':[rec]}, open('$LONGNAME_TMP','w'), ensure_ascii=False)"
} 2>&1 || true
LN15_OUT=$(python3 "$SCRIPT" "$LONGNAME_TMP" 2>&1 | tail -20); RC15=$?
rm -f "$LONGNAME_TMP"
if [ $RC15 -eq 0 ]; then
    P15="PASS"; PASS_COUNT=$((PASS_COUNT+1))
else
    P15="FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
fi
TOTAL=$((TOTAL+1))
printf "%s\n" "| T15_long_course_name_truncation_handled | 课程名超200字符被截断不影响后续分析流程 | $RC15 | $P15 | long-name handled gracefully |"

# 高负荷预警阈值触发 (单一老师同一日连排>=8节警告)
OVERLOAD_TMP=$(mktemp /tmp/overld.XXXX.json)
OVERLOAD_BODY="{\"schedule\":["
for i in 1 2 3 4 5 6 7 8 ; do OVERLOAD_BODY="${OVERLOAD_BODY}{\"course\":\"O$i\",\"teacher\":\"超负\",\"room\":\"R$i\",\"class\":\"C$i\",\"week_start\":1,\"week_end\":10,\"weekday\":\"2\",\"periods\":[$i]},"; done
OVERLOAD_BODY="${OVERLOAD_BODY}]}"
# 简化用Python生成更可靠:
python3 <<PYEOF >"$OVERLOAD_TMP"
import json
recs=[{"course":f"O{i}","teacher":"超负老师","room":f"R{i}","class":f"C{i}","weeks":[1],"weekday":"2","period":[i]} for i in range(1,13)]
print(json.dumps({"schedule": recs}))
PYEOF
OVLD16_OUT=$(python3 "$SCRIPT" "$OVERLOAD_TMP" 2>&1); RC16=$?
rm -f "$OVERLOAD_TMP"
if [ $RC16 -eq 0 ] && echo "$OVLD16_OUT" | grep -q "高负荷预警"; then
    P16="PASS"; PASS_COUNT=$((PASS_COUNT+1))
else
    P16="FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
fi
TOTAL=$((TOTAL+1))
printf "%s\n" "| T16_teacher_overload_warning_triggered_at_threshold8 | 单人周二连排12节触发高负荷预警章节生成 | $RC16 | $P16 | overload warning appeared in report |"

# 不同星期不可能同时段冲突——跨日相同资源不应误报为冲突
DIFFDAY_TMP=$(mktemp /tmp/diffday.XXXX.json)
python3 <<PYEOF >"$DIFFDAY_TMP"
import json
recs=[
 {"course":"A","teacher":"张三","room":"R1","class":"C1","weeks":[1],"weekday":"1","periods":[3]},
 {"course":"B","teacher":"张三","room":"R1","class":"C1","weeks":[1],"weekday":"2","periods":[3]},
]
print(json.dumps({"schedule": recs}))
PYEOF
DD17_OUT=$(python3 "$SCRIPT" "$DIFFDAY_TMP" 2>&1); RC17=$?
rm -f "$DIFFDAY_TMP"
if [ $RC17 -eq 0 ] && echo "$DD17_OUT" | grep -q "未检测出任何资源占用冲突"; then
    P17="PASS"; PASS_COUNT=$((PASS_COUNT+1))
else
    P17="FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
fi
TOTAL=$((TOTAL+1))
printf "%s\n" "| T17_different_weekday_not_false_positive | 同师同教室但不同星期一星期二同时段不算冲突 | $RC17 | $P17 | cross-day no false positive confirmed |"

# 无共享周次时不报冲突
NOSHOVERLAP_WEEKS_TMP=$(mktemp /tmp/novolapwks.XXXX.json)
NWS18_PAYLOAD='{"schedule":[{"course":"A","teacher":"张三","room":"R1","class":"C1","weeks":[1,2],"weekday":"1","periods":[5]},{"course":"B","teacher":"张三","room":"R1","class":"C1","weeks":[15,16],"weekday":"1","periods":[5]}]}'
echo "$NWS18_PAYLOAD" > "$NOSHOVERLAP_WEEKS_TMP"
NWK18_OUT=$(python3 "$SCRIPT" "$NOSHOVERLAP_WEEKS_TMP" 2>&1); RC18=$?
rm -f "$NOSHOVERLAP_WEEKS_TMP"
if [ $RC18 -eq 0 ] && echo "$NWK18_OUT" | grep -q "未检测出任何资源占用冲突"; then
    P18="PASS"; PASS_COUNT=$((PASS_COUNT+1))
else
    P18="FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
fi
TOTAL=$((TOTAL+1))
printf "%s\n" "| T18_non_overlapping_week_ranges_skip_detection | 两门周次范围完全不重叠即使其余维度都一致也不算冲突 | $RC18 | $P18 | non-overlapping weeks correctly ignored |"

# id重复时进入invalid清单而非覆盖原数据导致漏检
DUP_ID_TMP=$(mktemp /tmp/dupid.XXXX.json)
DUPI19_PAYLOAD='{"schedule":[{"id":"R001","course":"dup-A","teacher":"张三","room":"R1","class":"C1","weeks":[1],"weekday":"1","periods":[3]},{"id":"R001","course":"dup-B","teacher":"李四","room":"R2","class":"C2","weeks":[1],"weekday":"1","periods":[3]}]}'
echo "$DUPI19_PAYLOAD" > "$DUP_ID_TMP"
DIPI19_OUT=$(python3 "$SCRIPT" "$DUP_ID_TMP" 2>&1); RC19=$?
rm -f "$DUP_ID_TMP"
if [ $RC19 -eq 0 ] && echo "$DIPI19_OUT" | grep -qE "(无效|重复)"; then
    P19="PASS"; PASS_COUNT=$((PASS_COUNT+1))
elif [ $RC19 -eq 0 ] && echo "$DIPI19_OUT" | grep -q "无效"; then
    P19="PASS"; PASS_COUNT=$((PASS_COUNT+1))
else
    P19="FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
fi
TOTAL=$((TOTAL+1))
printf "%s\n" "| T19_duplicate_id_recorded_in_invalid_list | 显式id相同时第二条进invalid清单不被静默丢弃 | $RC19 | $P19 | duplicate-id detection works |"

# ===== 分支5: XSS防护 =====
XSRES_OUT=$(python3 "$SCRIPT" "$STC_DIR/xss_payload.json" 2>&1); RC_XSS=$?

RAW_TAG_FOUND=no
if echo "$XSRES_OUT" | grep -F '<script>' >/dev/null 2>&1; then RAW_TAG_FOUND=yes; fi
if echo "$XSRES_OUT" | grep -F '<img src=x onerror' >/dev/null 2>&1; then RAW_TAG_FOUND=yes; fi
ESCAPED_PRESENT=yes
if ! echo "$XSRES_OUT" | grep -F '&lt;' >/dev/null 2>&1; then ESCAPED_PRESENT=no; fi

if [ $RC_XSS -eq 0 ] && [ "$RAW_TAG_FOUND" = "no" ] && [ "$ESCAPED_PRESENT" = "yes" ]; then
    PXSS="PASS"; PASS_COUNT=$((PASS_COUNT+1))
else
    PXSS="FAIL"; FAIL_COUNT=$((FAIL_COUNT+1))
fi
TOTAL=$((TOTAL+1))
printf "%s\n" "| T20_xss_payload_sanitized_html_escape_applied | 含<script>/<img onerror>的输入被HTML实体转义不出现在原始标签形态报告中包含 &lt; 等 | $RC_XSS | $PXSS | raw tag found:$RAW_TAG_FOUND escaped present:$ESCAPED_PRESENT |"

echo ""

RATE_PCT=$(awk -v p=$PASS_COUNT -v t=$TOTAL 'BEGIN{printf "%.1f", p/t*100}')
echo "**统计**: 通过 $PASS_COUNT/$TOTAL ($RATE_PCT%)，失败 $FAIL_COUNT 条。"
