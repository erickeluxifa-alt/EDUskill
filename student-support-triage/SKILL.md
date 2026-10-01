---
name: student-support-triage
displayName: 学生事务分流与回复预览
description: 面向辅导员和学生服务人员，将多条学生咨询按主题、紧急度和责任角色分流，生成可审核的回复草稿与转交预览；纯离线运行，不发送消息或写入工单系统。
version: 1.0.0
author: ht
trigger:
  - 分流学生咨询
  - 整理学生事务工单
  - 给学生问题排优先级
  - 生成学生咨询回复草稿
  - 哪些学生问题需要马上处理
---

# 学生事务分流与回复预览

## 场景
面向辅导员、班主任、教务秘书、学生资助和心理支持服务人员，在一天内收到多条学生咨询、求助或事务申请时，快速形成可解释的优先级、责任队列和回复草稿。

## 输入
通过 `scripts/triage.py` 从标准输入接收 JSON：

```json
{
  "channel": "班级群收集",
  "items": [
    {"id": "Q01", "student": "S01", "text": "奖助学金申请材料什么时候交？"},
    {"id": "Q02", "student": "S02", "text": "我今天情绪很崩溃，想找老师聊聊"}
  ]
}
```

`items` 也可使用 `requests`；条目需要 `text`，建议提供稳定的 `id` 和脱敏后的 `student`。可选 `context`、`max_items`（1—100）和 `--pretty`。

## 处理逻辑
1. 校验数组和文本边界，清理控制字符，不输出原始敏感信息以外的额外推断。
2. 按关键词识别主题：心理支持、资助、学籍教务、住宿生活、就业实习、技术平台或其他。
3. 按显式紧急度和风险信号分级：`critical`（人身安全/自伤他伤/正在发生的重大危机）、`high`（时限临近、无法正常学习生活或明确求助）、`medium`（需要办理或解释的常规事务）、`low`（信息咨询）。
4. 结合主题与紧急度生成责任角色、建议首响动作、回复草稿和转交预览，并按优先级排序。
5. 对心理危机信号只提示“立即联系学校既有危机处置渠道并人工确认”，不诊断、不承诺保密、不替代专业人员。

## 输出
JSON 包含 `summary`、`queue`、`reply_drafts`、`handoff_preview`、`side_effects`。每项含 `id`、`topic`、`urgency`、`reason`、`owner_role`、`recommended_action`、`draft_reply`、`status`。

## 交互与边界
- 仅生成预览，不发送回复、不创建工单、不联系家长、不修改学生档案。
- 缺少 `items/requests`、数组为空或条目缺少文本时返回 `INVALID_INPUT`。
- 关键词分流不是正式风险评估；紧急度、责任人和回复必须由人工复核。
- 示例数据为模拟数据，未接入学校统一身份、教务、资助、心理或工单系统。

## 使用
```bash
python3 scripts/triage.py --pretty < examples/sample.json
```
