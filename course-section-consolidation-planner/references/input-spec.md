# 输入与输出规范

## 输入 JSON

```json
{
  "policy": {
    "max_progress_gap": 1,
    "allow_cross_campus": false,
    "review_score_below": 75
  },
  "sections": [],
  "students": [],
  "candidates": []
}
```

### sections

每个教学班包含：
- `id`：唯一字符串。
- `course_code`：课程代码；候选组内必须一致。
- `enrollment`：非负整数。
- `capacity`：正整数。
- `timeslots`：字符串数组，如 `Mon-1-2`。
- `progress_week`：非负整数。
- `language`：授课语言。
- `campus`：校区。
- `teacher_id`：匿名教师 ID。
- `teacher_load`：当前周课时，非负数。
- `room_id`：教室标识，可空。

### students

每个学生包含：
- `id`：匿名唯一 ID。
- `section_id`：当前教学班。
- `external_timeslots`：学生其他课程占用时段数组。

### candidates

每个候选包含：
- `id`：方案 ID。
- `section_ids`：至少两个教学班 ID。
- `target_section_id`：承接合并的教学班 ID，必须属于 `section_ids`。
- `room_capacity`：可选；指定调整后的教室容量。

## 输出 JSON

顶层字段：
- `summary`：候选总数、推荐数、复核数、阻断数。
- `results`：逐候选结果。
- `data_issues`：输入数据问题。

逐候选字段：
- `candidate_id`、`status`、`score`。
- `merged_enrollment`、`effective_capacity`、`utilization`。
- `blockers`、`risks`、`affected_students`。
- `confirmation_items`。

## 状态语义

- `recommended`：无阻断且得分达到复核阈值。
- `review`：无阻断但得分低于阈值，需要重点人工复核。
- `blocked`：存在硬约束冲突，不应进入执行流程。

## 边界与限制

- 时间段采用完全匹配，不推断重叠关系。
- 教师负荷只作为风险扣分，不判断劳动合同或绩效规则。
- 不识别课程内容语义，仅用课程代码和进度周做显式核对。
- 若学校政策不同，应调整输入阈值或脚本规则后重新验证。
