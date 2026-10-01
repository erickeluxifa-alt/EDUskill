---
name: family-communication-rehearsal
displayName: 家校沟通预演器
description: 面向班主任和任课教师，将匿名化的学生表现事实整理为可审核的家校沟通议程、事实陈述、开放式问题、支持建议和行动项。适用于家长会、电话沟通或阶段性反馈前的准备；纯离线运行，只生成预览，不发送消息、不作诊断或纪律判断。
version: 1.0.0
author: ht
trigger:
  - 帮我准备家校沟通
  - 生成家长沟通话术
  - 预演一次家长电话
  - 整理家长会谈议程
  - 把学生表现整理成家校沟通草稿
---

# 家校沟通预演器

把分散的学习、出勤、课堂和支持记录整理为一次中性、具体、可确认的沟通预览。

## 使用流程

1. 收集 JSON 输入；只使用完成任务所需的最少信息，建议使用化名或校内受控标识。
2. 运行 `scripts/rehearse.py`，生成 Markdown 和结构化 JSON 预览。
3. 检查事实日期、敏感措辞、待核实推断和隐私提醒。
4. 教师人工确认沟通对象、渠道、事实范围、措辞和行动项后，再在线下或学校认可系统中执行。
5. 本 Skill 不发送消息、不联系家长、不写回 LMS/SIS。

## 输入契约

```json
{
  "class_name": "八年级2班",
  "student": {"id": "S001", "name": "示例甲"},
  "context": {"channel": "phone", "purpose": "阶段性学习反馈"},
  "observations": [
    {"date": "2026-09-08", "domain": "作业", "fact": "本周4次作业中2次按时提交", "source": "作业记录"},
    {"date": "2026-09-10", "domain": "课堂", "fact": "小组讨论中完成了资料整理", "source": "课堂观察"}
  ],
  "strengths": ["资料整理较细致"],
  "support_options": ["提供一周任务清单"],
  "requested_actions": ["家校共同确认每日20分钟补交安排"]
}
```

必填：`student`、非空 `observations`。每条观察需包含 `date`、`domain`、`fact`；日期为 `YYYY-MM-DD`。可选：`context`、`strengths`、`support_options`、`requested_actions`。输入文件不超过 1 MB，各数组最多 20 项，超限会明确拒绝而非截断。

## 执行

```bash
python3 scripts/rehearse.py examples/sample_input.json --out-dir output
python3 scripts/rehearse.py examples/sample_input.json --json
```

## 输出契约

- `communication_preview.json`：校验状态、议程、事实卡、开放式问题、支持建议、行动项、风险提示与确认清单。常规状态为 `REVIEW_REQUIRED`；安全信号状态为 `SAFETY_ESCALATION_REQUIRED`，并设置 `must_stop: true`。
- `communication_preview.md`：可直接预演的沟通顺序，但始终标记为“待人工确认”；安全状态仅保留事实、风险复核与人工升级指引。
- 风险提示识别标签化、诊断性、绝对化或责备性措辞；命中内容保留用于教师复核，不自动发送。

## 边界与异常

- 缺少学生或观察事实、日期错误、字段类型错误时返回明确错误，不生成可执行草稿。
- 文本会移除控制字符、限制长度，并在 Markdown 中转义 HTML，降低 XSS 风险。
- 不推断家庭原因、健康诊断、心理状态或主观动机；未知原因转成开放式核实问题。
- 不处理紧急安全事件；若输入出现人身安全信号，结果会提示立即转学校既有人工处置流程。
- 所有结果仅供教师预览，不构成对学生或家庭的评价结论。
