---
name: teaching-quality-closure
display_name: 教学质量整改闭环助手
description: 将督导、课程评价、问卷或教学检查发现转成分级整改台账，给出责任角色、动作、目标日期和复核证据；默认只生成预览，不写入外部系统。
version: 1.0.0
---

# 教学质量整改闭环助手

## 场景
面向院系负责人、教学秘书、教研组长和教师，在课程评价、听课督导、教学检查或学生反馈后，快速形成可执行、可复核的整改清单。

## 触发方式
- “把这些督导问题整理成整改台账”
- “分析课程评价并给出整改优先级”
- “生成教学质量问题闭环清单”
- “哪些教学问题先处理，谁负责，什么时候复核？”

## 输入
优先使用 JSON：
```json
{"findings":[{"description":"学生反馈课程目标与作业要求不一致","severity":"high","owner":"课程负责人"}]}
```
也支持将自然语言问题逐条整理为 `findings`。每项可包含 `description`/`issue`/`finding`、`severity`、`owner`、`due_date`。可选 `max_items`，范围 1—100。

## 处理逻辑
1. 校验输入为非空问题数组，并丢弃空描述。
2. 按显式严重程度或关键词映射为 critical/high/medium/low。
3. 按关键词归类为课程目标、考核、课堂、实践、资源、数据或学生支持问题。
4. 根据严重程度给出保守的目标日期建议，保留用户提供的责任人和日期。
5. 生成排序后的整改台账、通用复核证据和人工确认队列。
6. 所有项目状态为“待确认”，明确不发送通知、不写入教务或质量系统。

## 输出
通过 `scripts/quality_closure.py` 从标准输入接收 JSON，输出 JSON，包含：`summary`、`register`、`review_queue`、`side_effects`。台账每项包含 `id`、`finding`、`category`、`severity`、`priority_score`、`owner`、`recommended_action`、`target_date`、`evidence_to_close`、`status`。

## 交互与边界
- 生成、发送、提交、批量修改前必须展示预览并等待人工确认；本 Skill 只做预览。
- 缺少 `findings/issues`、数组为空或条目无描述时返回 `INVALID_INPUT`。
- 不替代学校正式质量标准；严重程度和日期是建议值，应由教学管理者确认。
- 不接入真实 SIS/LMS、消息系统或数据库，示例均为模拟数据。

## 最小验证
```bash
printf '%s' '{"findings":[{"description":"课程目标与作业要求不一致","severity":"high"},{"description":"个别学生无法访问实验资源","severity":"medium"}]}' | python3 scripts/quality_closure.py
printf '%s' '{"findings":[]}' | python3 scripts/quality_closure.py
```
