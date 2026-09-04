---
name: research-milestone-risk-radar
displayName: 科研节点风险雷达
description: 面向研究生导师、科研项目负责人和科研秘书，依据项目节点、负责人进展、依赖关系与截止日期，识别逾期/临近/阻塞风险并生成可确认的行动清单。支持本地 JSON 离线分析，不自动修改或提交外部系统。
version: 1.0.0
author: ht
trigger:
  - 检查科研项目节点风险
  - 分析研究生科研进度
  - 哪些科研任务要延期
  - 生成科研项目跟进清单
  - 看看课题组有哪些节点卡住了
---

# 科研节点风险雷达

## 场景
导师、科研项目负责人或科研秘书在周例会、月度检查、开题/中期/结题前，导入一份项目节点清单，快速得到需要优先跟进的人、节点和原因。

## 输入
JSON 文件可为数组，也可为 `{ "milestones": [...] }`。每条节点至少包含：

```json
{
  "id": "M-001",
  "project": "智能教学研究",
  "milestone": "完成访谈编码",
  "owner": "李同学",
  "due_date": "2026-08-28",
  "status": "in_progress",
  "progress": 0.65
}
```

可选字段：`blocked_by`（依赖节点 ID 数组）、`last_update`、`priority`（1-5）、`evidence`。状态支持 `planned`、`in_progress`、`blocked`、`done`、`cancelled`。

## 执行

```bash
python3 scripts/radar.py examples/sample_milestones.json
python3 scripts/radar.py examples/sample_milestones.json --json
python3 scripts/radar.py examples/sample_milestones.json --as-of 2026-08-30 --window-days 7 --preview
```

## 输出
- 数据校验摘要和字段问题；
- 项目/负责人维度的风险统计；
- 每个风险节点的等级、原因、证据和建议动作；
- 未来窗口内的节点拥堵提示；
- `--preview` 输出拟跟进动作的预览，明确需要人工确认后再发送/写回；`--json` 输出结构化结果，便于页面或其他 Skill 组合调用。

## 规则
1. `done` 和 `cancelled` 不进入待跟进风险清单。
2. 截止日早于分析日且未完成：高风险；距截止日 0-3 天且进度低于 0.8：高风险；距截止日 4-7 天且进度低于 0.6：中风险。
3. `blocked` 或依赖节点未完成时至少为中风险；依赖节点也逾期时升级为高风险。
4. 进度低于 0.3 且距截止日不超过 14 天时为中风险；无进度字段但已临近/逾期时标记“信息不足”，不臆测完成度。
5. 同一项目未来 7 天内有 3 个及以上未完成节点，提示排期拥堵；同一负责人有 4 个及以上未完成节点，提示负荷集中。
6. 建议动作仅为人工跟进、补充证据、重排日期、拆分任务或协调依赖，不自动变更数据。

## 安全与限制
纯 Python 标准库、离线运行；日期必须为 `YYYY-MM-DD`。报告中的用户文本会做长度限制和 Markdown 清洗，避免控制字符/表格注入。示例数据均为模拟数据，不接入真实科研管理系统，不替代导师判断，也不将风险分级作为学生评价或处分依据。

## 可组合接口
`--json` 的 `risks`、`congestion`、`summary` 可供科研周报、项目看板或消息预览组件读取。外部系统适配应放在独立适配层，并在写入/发送前保留二次确认。
