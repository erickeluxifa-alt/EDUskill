---
name: lesson-runbook-builder
displayName: 课堂授课运行单生成器
description: 将教案、课程目标和活动信息转换为可直接执行的课堂授课运行单，包含时间轴、师生动作、形成性检查、差异化支持和异常预案；离线运行，不连接 LMS/SIS，不自动发布或发送。
version: 1.0.0
author: ht
entrypoint: scripts/build_runbook.py
---

# 课堂授课运行单生成器

## 场景
面向教师、班主任和教研员，在课前已有教案或课程目标但需要快速落地授课时，把“内容计划”转换为课堂现场可照着执行的运行单，降低临场组织成本。

## 触发方式
- “把这份教案转换成课堂授课运行单”
- “给我一份 45 分钟课程的课堂流程和检查点”
- “为这节课生成教师动作、学生产出和异常预案”
- “把课程目标拆成可执行的课堂节奏”

## 输入
通过 `scripts/build_runbook.py` 接收 JSON。核心字段：`course`、`lesson`、`duration_minutes`、`objectives`；可选 `audience`、`class_size`、`activities`、`resources`、`constraints`。

`activities` 中每项可含 `name`、`minutes`、`mode`、`student_output`、`objective_refs`。若缺少活动，脚本根据目标生成保守的导入、建模/讲解、练习、检查、收束五段式运行单，并明确这是默认假设。

## 处理逻辑
1. 校验课程、课题、时长和目标；拒绝空目标、非正时长及超过 240 分钟的输入。
2. 优先保留用户活动顺序，补齐缺少的教师动作、学生产出、检查点和转场提示。
3. 对活动时长求和；超出总课时则返回 `needs_revision` 和超时问题，不擅自压缩用户数据。
4. 根据目标类型与课堂模式生成可观察证据：口头回应、练习产出、出口条或快速演示。
5. 生成低风险异常预案：进度落后、学生无响应、资源不可用；所有动作均为预览。
6. 输出稳定的 JSON，或通过 `--format md` 输出便于课堂打印/复制的 Markdown。

## 输出
包含 `status`、`summary`、`timeline`、`checkpoints`、`differentiation`、`contingencies`、`issues`、`assumptions`、`side_effects`。每个时间段包含 `start_minute`、`end_minute`、`teacher_actions`、`student_actions`、`student_output`、`check_for_understanding`。

## 交互与限制
- 只生成运行单预览，不写入 LMS/SIS、不发送通知、不修改成绩或课表。
- 缺少目标时返回 `INVALID_INPUT`；活动超时或目标引用不存在时返回 `needs_revision`。
- 默认活动与建议检查点是启发式草案，须由任课教师结合学科、班级和无障碍要求复核。
- 示例仅使用模拟数据，不含真实学生姓名、成绩、账号或凭据。

## 使用
```bash
python3 scripts/build_runbook.py examples/sample_input.json --format md
python3 scripts/build_runbook.py examples/sample_input.json --format json
printf '%s' '{"course":"概率论","lesson":"条件概率","duration_minutes":45,"objectives":["能用公式计算条件概率"]}' | python3 scripts/build_runbook.py - --format md
```
