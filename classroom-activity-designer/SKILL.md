---
name: classroom-activity-designer
description: 课堂活动设计包生成器。何时使用：教师、教研员或班主任需要根据课程主题、学生规模、课时、教学目标和课堂限制，快速设计可直接执行的小组活动、讨论、案例、练习或展示流程时使用；也适用于把已有教案目标转成时间轴、分工、教师提示语、学生产出和评价量规。支持同义表达如课堂活动设计、课堂互动方案、分组讨论、教学活动脚本、课堂任务单。离线运行，不连接真实 LMS/SIS。
---

# 课堂活动设计包生成器

将结构化课程要求转成一份可预览、可修改、可复用的课堂活动设计包。

## 工作流

1. 收集 `course`、`topic`、`duration_minutes`、`student_count`、`objectives`；缺少限制时使用保守默认值，并在输出中标注假设。
2. 读取 `references/activity-rules.md`，按目标动词选择活动模式：理解优先概念排序/同伴解释，应用优先案例决策，分析优先证据辩论，创造优先方案工作坊。
3. 通过 `scripts/design_activity.py` 生成 Markdown 方案和结构化 JSON。脚本只使用 Python 标准库，不读取网络、环境变量或任意用户路径。
4. 方案必须包含：活动目标、课前准备、时间轴、分组与角色、教师提示语、学生产出、评价量规、异常分支、课后延伸和预览确认项。
5. 对生成结果做预览：涉及改变分组、对外发布、写入 LMS 或发送通知时，只输出待确认动作，不执行外部副作用。
6. 若输入缺失关键字段或数值非法，返回可修复的错误清单，不生成看似完整的方案。

## 输入契约

```json
{
  "course": "课程名称",
  "topic": "本节主题",
  "duration_minutes": 45,
  "student_count": 48,
  "objectives": ["解释...", "应用..."],
  "constraints": {"room": "固定座位", "devices": "每组1台", "special_needs": ""},
  "preferred_mode": "auto"
}
```

## 输出契约

返回对象包含 `status`、`assumptions`、`activity`、`markdown`。`activity` 具备稳定字段：`mode`、`timeline`、`groups`、`teacher_prompts`、`student_outputs`、`rubric`、`contingencies`、`confirmation`。`status` 为 `ok` 或 `error`。

## 参考与示例

- 设计规则和边界：见 `references/activity-rules.md`
- 最小输入示例：见 `examples/sample_input.json`
- 运行方式和交付说明：见 `README.md`
