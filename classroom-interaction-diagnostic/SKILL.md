---
name: classroom-interaction-diagnostic
displayName: 课堂互动证据诊断
description: 根据课堂互动记录或汇总数据，诊断学生参与证据的覆盖、分层与缺口，生成下一节课可执行的低风险干预建议和人工确认跟进预览；纯离线运行，不替代教师判断。
version: 1.0.0
author: ht
trigger:
  - 分析课堂互动情况
  - 哪些学生课堂参与不足
  - 根据课堂记录设计下一节课干预
  - 生成课堂参与诊断
  - 看看课堂互动证据覆盖情况
---

# 课堂互动证据诊断

## 场景
面向任课教师、班主任、教研员，在一节课或一周课程结束后，根据点名、发言、提问、随堂提交、同伴协作等可观察记录，快速识别“尚无足够证据”的学生，并生成下一节课可执行的参与机会安排。

## 输入
通过 `scripts/diagnose.py` 从标准输入接收 JSON：

```json
{
  "course": "数据结构",
  "class_name": "计科2401",
  "sessions": [{
    "name": "张三", "student_id": "S01", "attendance": "present",
    "speak": 0, "question": 1, "submission": 1, "collaboration": 0,
    "note": "小组活动中有观察记录"
  }]
}
```

`sessions` 也可使用 `students` 别名；证据字段可接受布尔值或非负数字。`attendance` 支持 `present`/`absent`/`late`/`unknown`，缺失按 `unknown` 处理。可用 `--pretty` 美化输出。

## 处理规则
1. 校验非空学生数组，清洗控制字符并限制文本长度；保留原始记录不写回外部系统。
2. 出勤为 `absent` 的学生不因缺少互动证据被判为低参与，标记为“缺席，不评价”。
3. 参与分 `0.30×发言 + 0.20×提问 + 0.25×随堂提交 + 0.25×协作`，每项按“有证据=1，无证据=0”封顶归一化；迟到学生保留证据但提示核对。
4. 分层：`>=0.75` 证据充分，`0.40-0.74` 证据有限，`<0.40` 需要增加机会；无互动字段则为“数据不足”。
5. 只输出“证据不足/待补证据”，不推断学习能力、态度、性格或最终成绩；单次记录不足以形成稳定结论。
6. 对“需要增加机会”生成轮换式建议：低风险冷启动提问、匿名提交、同伴核对、课后可选补充；跟进动作均为待教师确认的预览。

## 输出
结果包含 `summary`（人数、出勤、证据覆盖、层级计数）、`students`（分数、层级、缺口、建议）、`intervention_plan`（下一节课建议）、`review_queue`（待确认跟进）、`side_effects`（明确无外部写入/通知）。

## 交互与边界
- 仅生成预览，不发送消息、不修改成绩、不写入 LMS/SIS。
- 缺少 `sessions`/`students`、数组为空或记录缺少姓名与可识别 ID 时返回 `INVALID_INPUT`。
- 这是形成性教学辅助，不是学生评价、处分或自动预警依据；建议至少合并 3 次课或教师观察后再做持续判断。
- 示例数据为模拟数据，未接入真实课堂系统。

## 使用
```bash
python3 scripts/diagnose.py < examples/sample.json
python3 scripts/diagnose.py --pretty < examples/sample.json
```
