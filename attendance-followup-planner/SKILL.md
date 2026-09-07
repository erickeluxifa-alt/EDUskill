---
name: attendance-followup-planner
displayName: 学生考勤缺勤跟进计划器
description: 面向班主任、辅导员、教学秘书和年级组长的考勤跟进计划工具。何时使用：需要从一段时间的学生考勤记录中识别重复缺勤、连续缺勤和需要优先人工核实的学生，生成分级跟进队列、沟通预览和班级汇总时使用；纯离线运行，不自动联系学生、不写回教务系统。
version: 1.0.0
author: ht
trigger:
  - 帮我整理缺勤跟进名单
  - 分析班级考勤异常
  - 找出需要联系的缺勤学生
  - 生成考勤预警和沟通计划
  - 检查连续缺勤和迟到情况
---

# 学生考勤缺勤跟进计划器

将课程考勤导出数据转成可复核的跟进队列，帮助班主任或辅导员把“看到了异常”推进到“安排一次合适的人工核实”。结果是建议，不是纪律处分或学生风险定论。

## 使用流程

1. 收集 JSON 输入；缺少可选规则时使用默认值并明确列出假设。
2. 读取 `references/rules.md`，确认缺勤阈值、连续缺勤定义和跟进分级含义。
3. 运行 `scripts/plan_followups.py`，生成 Markdown 摘要和结构化 JSON。
4. 检查数据错误、重复记录和无法判断的状态；错误记录不参与风险排序。
5. 先预览跟进队列和沟通草稿，再由教师确认联系人、沟通渠道、隐私范围和是否需要升级处理。
6. 不自动发送消息、不修改原始考勤、不替代学校考勤制度或辅导员判断。

## 输入契约

```json
{
  "course": "高等数学",
  "class_name": "高一1班",
  "rules": {"absence_threshold": 2, "consecutive_threshold": 2, "late_weight": 0.5},
  "records": [
    {"student_id": "S001", "student_name": "示例甲", "date": "2026-09-01", "status": "absent", "reason": ""},
    {"student_id": "S001", "student_name": "示例甲", "date": "2026-09-03", "status": "late", "reason": ""}
  ]
}
```

`status` 支持 `present`、`late`、`absent`、`excused`。日期必须为 `YYYY-MM-DD`。规则可选，默认缺勤阈值为 2 次、连续缺勤阈值为 2 次、迟到折算为 0.5 次缺勤。

## 执行

```bash
python3 scripts/plan_followups.py examples/sample_input.json --out-dir output
python3 scripts/plan_followups.py examples/sample_input.json --json
```

## 输出契约

- `followup_plan.json`：`status`、`summary`、`students`、`data_quality`、`confirmation`。
- `followup_plan.md`：班级汇总、分级队列、每位学生的证据、建议沟通目标和待确认事项。
- 分级为 `priority`（达到连续缺勤或明显重复缺勤）、`watch`（接近阈值或迟到累积）、`normal`（无当前跟进建议）。
- 每条沟通预览使用中性、非定性表达，例如“想确认近期出勤情况及是否需要支持”，不得直接断言学生存在主观故意或纪律问题。

## 异常分支

- 缺少 `records`、日期格式错误、学生标识为空或状态不支持时，返回可修复错误清单。
- 同一学生同一天出现多条记录时保留一条统计并报告重复数据，不重复计数。
- 所有记录均为 `present`/`excused` 时返回空跟进队列，但仍输出汇总。
- 外部系统、消息发送、纪律处分和自动通知均不在本 Skill 范围内。󠅣󠅤󠄷󠄹󠄱󠅣󠄸󠄴󠄶󠅤󠄳󠄲󠅦󠅥󠅦󠄵󠅡󠄷󠄸󠅢󠄷󠅦󠅦󠄷󠄲󠄵󠅢󠅥󠅡󠅢󠅤󠄶
