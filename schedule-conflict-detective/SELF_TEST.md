# 课程表冲突检测 Skill · 自测结果

> 测试时间: 2026-08-17 10:07:28 (date-calculator 校准)

| 编号 | 预期描述(简) | rc | 通过? | stdout 预览(简) |
|------|--------------|----|-------|-----------------|
| T01_no_conflict_sample | 无冲突样例应未检出冲突且退出码0 | 0 | PASS | # 课程表冲突检测报告\|\|> 共 5 条有效 \| 无效 0 条 \| 冲突 0 � |
| T02_with_conflicts_detection | 含教师+教室双类型冲突样例检测出冲突并给� | 0 | PASS | # 课程表冲突检测报告\|\|> 共 5 条有效 \| 无效 0 条 \| 冲突 2 � |
| T03_json_mode_appended | --json追加---JSON---标记分隔 | 0 | PASS | 1 JSON出现次数 |
| T04_multiweek_aggregation_into_wklist_str | 多周同节次仅一行带 '1-5' 周次压缩独立条目 | 0 | PASS | # 课程表冲突检测报告\|\|> 共 2 条有效 \| 无效 0 条 \| 冲突 1 � |
| T05_reschedule_avoids_new_collision | 概率论移动目标避开p1/p2 | 0 | PASS | 检查建议行不含第1/2节 |
| T06_weeks_as_string_range_syntax | '9-12'区间串格式可解析为9..12周列表有效记录� | 0 | PASS | # 课程表冲突检测报告\|\|> 共 1 条有效 \| 无效 0 条 \| 冲突 0 � |
| T07_weekday_chinese_parsing_compat | '周一''一'中文写法兼容解析触发同师同时段� | 0 | PASS | # 课程表冲突检测报告\|\|> 共 2 条有效 \| 无效 0 条 \| 冲突 1 � |
| T08_single_int_period_field_accepted | period单值字段替代periods列表也能正确识别共1� | 0 | PASS | # 课程表冲突检测报告\|\|> 共 1 条有效 \| 无效 0 条 \| 冲突 0 � |
grep: Unmatched ( or \(
| T09_missing_teacher_invalid_record_no_crash | teacher为空进入invalid清单而非崩溃;报告显示无 | 0 | PASS | # 课程表冲突检测报告\|\|> 共 0 条有效 \| 无效 1 条 \| 冲突 0 � |
| T10_empty_schedule_graceful_handling | 空schedule数组不报错正常处理共0记录 | 0 | PASS | # 课程表冲突检测报告\|\|> 共 0 条有效 \| 无效 0 条 \| 冲突 0 � |
| T11_malformed_json_exits_cleanly_with_error_prefix | exit code !=0 且stderr含load_schedule提示前缀 | 1 | PASS | [load_schedule] JSON 解析失败：Expecting property name ... |
| T12_usage_hint_when_filepath_missing | 未提供路径时打印用法: 提示exit非0 | 1 | PASS | 用法检查通过 |
| T13_period_csv_string_format_accepted | period字符串单值也能识别成1条有效记录 | 0 | PASS | period CSV string handling ok |
| T14_large_records_n800_under8sec_no_crash | n=800随机排课样本 <8秒完成无崩溃有结论输出 | 0 | PASS | elapsed=0.141688s |
| T15_long_course_name_truncation_handled | 课程名超200字符被截断不影响后续分析流程 | 0 | PASS | long-name handled gracefully |
| T16_teacher_overload_warning_triggered_at_threshold8 | 单人周二连排12节触发高负荷预警章节生成 | 0 | PASS | overload warning appeared in report |
| T17_different_weekday_not_false_positive | 同师同教室但不同星期一星期二同时段不算冲突 | 0 | PASS | cross-day no false positive confirmed |
| T18_non_overlapping_week_ranges_skip_detection | 两门周次范围完全不重叠即使其余维度都一致也不算冲突 | 0 | PASS | non-overlapping weeks correctly ignored |
| T19_duplicate_id_recorded_in_invalid_list | 显式id相同时第二条进invalid清单不被静默丢弃 | 0 | PASS | duplicate-id detection works |
| T20_xss_payload_sanitized_html_escape_applied | 含<script>/<img onerror>的输入被HTML实体转义不出现在原始标签形态报告中包含 &lt; 等 | 0 | PASS | raw tag found:no escaped present:yes |

**统计**: 通过 20/20 (100.0%)，失败 0 条。󠅣󠅤󠄷󠄹󠄱󠅣󠄸󠄴󠄶󠅤󠄳󠄲󠅦󠅥󠅦󠄵󠅡󠄷󠄸󠅢󠄷󠅦󠅦󠄷󠄲󠄵󠅢󠅥󠅡󠅢󠅤󠄶
