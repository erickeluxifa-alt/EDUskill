---
name: assessment-moderation-auditor
displayName: 课程成绩审核与补救建议
description: 面向教师、教务秘书和院系负责人，在成绩提交前审核多项成绩、权重和考勤数据，发现缺失、越界、总评异常与补救候选，输出可复核的审核报告；纯离线运行，不自动修改或提交成绩。
version: 1.0.0
author: ht
trigger:
  - 帮我审核这门课的成绩
  - 成绩提交前检查
  - 检查总评有没有异常
  - 找出缺考和补考候选人
  - 复核成绩单里的问题
---
# 课程成绩审核与补救建议

## 场景
教师或教务在录入/提交课程成绩前，将各评价项、权重、考勤和可选人工总评导出为 JSON，快速得到“可通过、需人工复核、建议补救”的清单。适用于高校课程、职业教育课程和基础教育阶段性评价的预提交检查。

## 输入
```json
{
  "course": "数据库原理",
  "rules": {"pass_mark": 60, "attendance_min": 70, "weights": {"平时": 0.3, "期末": 0.7}},
  "students": [
    {"id": "S001", "name": "示例甲", "scores": {"平时": 78, "期末": 62}, "attendance": 92, "reported_total": 67}
  ]
}
```
`weights` 必须合计 1；成绩项必须是 0-100 数字；缺失成绩用 `null` 或空字符串；`reported_total` 可省略。示例仅使用模拟学生。

## 执行
```bash
python3 scripts/audit_assessment.py --demo
python3 scripts/audit_assessment.py --input examples/sample.json --out-dir output
python3 scripts/audit_assessment.py --input examples/sample.json --strict --json
```

## 输出
- `review.json`：结构化审核结果，可供后续页面或教务适配层使用。
- `review.md`：摘要、问题清单、补救候选和人工确认事项。

问题分为：`data_error`（输入数据错误）、`manual_review`（需人工核验）、`remediation_candidate`（按规则建议补救，不代表最终结论）。

## 核心规则
1. 权重不为 1、成绩越界、重复学号、空学生记录属于输入错误；默认保留其他记录并报告，`--strict` 下直接退出。
2. 总评按各项成绩×权重计算，缺失任一必需项时不计算总评，并标记待补数据。
3. 有 `reported_total` 时，与计算总评相差超过 0.5 分标记为人工复核。
4. 计算总评低于 `pass_mark` 标记为补救候选；低于及格线 5 分以内标记“接近及格”，更低标记“需重点关注”。
5. 考勤低于 `attendance_min`、所有成绩缺失或考勤缺失仅触发人工复核，不自动推断缺考/处分。

## 交互与边界
本工具不写回源文件、不发送通知、不连接 LMS/SIS，结果只作为提交前预览。教师需人工确认成绩政策、补考资格、隐私范围和最终提交动作。输入文本会转义后写入 Markdown；无第三方依赖、无网络、无 shell/eval。
