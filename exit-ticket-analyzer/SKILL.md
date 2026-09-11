---
name: exit-ticket-analyzer
displayName: 课后小测分层分析
description: 面向教师和教研员，分析课后小测或 Exit Ticket 的逐题作答数据，识别知识点掌握分层、共性错误与下一课补救分组，输出可审核的形成性教学预览；纯离线运行，不修改成绩或发送通知。
version: 1.0.0
author: ht
trigger:
  - 分析课后小测
  - 看看 exit ticket 结果
  - 根据随堂小测安排下一节课
  - 找出学生的共性错误
  - 生成课后小测分层报告
---

# 课后小测分层分析

## 场景
面向任课教师、班主任和教研员，在一节课结束后将 3-10 题的形成性小测结果转成可行动的下一课分组。工具回答“哪些知识点需要再教、哪些学生需要哪种支持”，不把一次小测当作正式成绩或稳定能力判断。

## 输入
通过 `scripts/analyze_exit_ticket.py` 接收 JSON：

```json
{
  "course": "概率论",
  "lesson": "条件概率",
  "questions": [
    {"id":"Q1","topic":"事件定义","max_score":1},
    {"id":"Q2","topic":"条件概率公式","max_score":1}
  ],
  "students": [
    {"id":"S01","name":"示例甲","answers":{"Q1":1,"Q2":0}},
    {"id":"S02","name":"示例乙","answers":{"Q1":1,"Q2":1}}
  ]
}
```

分数可为 0~`max_score` 的数字；缺答可用 `null`、空字符串或省略。题目必须有唯一 `id`、正数满分和非空 `topic`。

## 处理规则
1. 校验并截断：最多 1000 名学生、100 道题；非法题目不参与计算并列入问题清单。
2. 逐题计算得分率和缺答率；按知识点聚合，使用该知识点题目的平均得分率。
3. 学生总得分率分层：`>=0.8` 掌握较好，`0.5-0.79` 部分掌握，`<0.5` 需要支持；有效作答题少于总题数一半时标记“证据不足”。
4. 知识点按得分率排序：低于 0.5 为优先再教，0.5-0.79 为巩固，至少 0.8 为保持；同分按知识点名称稳定排序。
5. 分组只依据本次答题证据：优先支持组安排示范/分步练习，巩固组安排同伴解释/变式题，掌握组安排迁移题或小导师角色；教师需确认分组与学生隐私边界。
6. 不推断学生智力、态度、诊断或最终成绩，不自动发布、改分、通知或写入 LMS/SIS。

## 输出
运行 `--out-dir` 生成 `exit_ticket_report.json` 和 `exit_ticket_report.md`，包含 `summary`、`question_analysis`、`topic_analysis`、`students`、`next_lesson_plan`、`review_items`、`side_effects`。

## 使用
```bash
python3 scripts/analyze_exit_ticket.py --demo --json
python3 scripts/analyze_exit_ticket.py --input examples/sample_input.json --out-dir output
python3 scripts/analyze_exit_ticket.py --input examples/sample_input.json --strict
```

## 限制与依赖
仅依赖 Python 3 标准库，不联网。示例数据为模拟数据。建议至少结合连续 2-3 次形成性证据和教师观察再做持续性教学判断；本工具结果须由教师人工复核。
