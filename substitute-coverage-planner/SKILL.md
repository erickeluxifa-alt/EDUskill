---
name: substitute-coverage-planner
displayName: 教师缺勤代课与调课方案生成
version: 1.0.0
author: ht
description: 面向教务处、院系教学秘书和年级组长，在教师临时缺勤时，根据课表、代课教师资质与忙闲、教室容量和日负荷生成可解释的代课/调课候选方案及冲突清单；纯离线预览，不写回教务系统。
trigger:
  - 老师请假了帮我安排代课
  - 生成缺勤课程的代课方案
  - 检查代课老师有没有时间冲突
  - 给这些停课安排补课时段
  - 排一个教师缺勤覆盖方案
---
# 教师缺勤代课与调课方案生成

## 场景
教师临时请假后，教务处、院系教学秘书或年级组长需要在短时间内覆盖受影响课程。Skill 同时考虑学科/课程资质、教师忙闲、最大日负荷、时段偏好、教室容量和班级冲突，优先生成代课方案；无法代课时给出可复核的调课候选，不把冲突留到通知阶段。

适用于高校、职业院校及中小学的日常代课协调。默认上限为 300 门受影响课程、500 位候选教师和 1000 个可用时段。

## 输入
```json
{
  "date_range": "2026-09-14~2026-09-18",
  "absences": [{"teacher_id":"T01","course_id":"C01","class_id":"CL1","subject":"数学","slot":"Mon-1","room_id":"R1","students":42}],
  "teachers": [{"id":"T02","name":"教师乙","subjects":["数学"],"available_slots":["Mon-1"],"max_daily_load":4,"existing_load":{"Mon":2}}],
  "rooms": [{"id":"R1","capacity":50,"available_slots":["Mon-1","Tue-3"]}],
  "class_busy": {"CL1":["Tue-1"]},
  "makeup_slots": ["Tue-3","Wed-2"],
  "rules": {"allow_cross_subject":false,"max_candidates":3}
}
```

`absences`、`teachers` 必填。课程、教师和教室 ID 必须非空；学生数须为非负整数。`slot` 使用 `Day-Period`（如 `Mon-1`）。教师未声明 `available_slots` 即视为不可用，而非默认全天可用。

## 处理
1. 校验重复缺勤、未知教师、非法时段、重复 ID、容量和负荷字段；错误记录不进入排程。
2. 为每门受影响课程筛选同学科且原时段可用的教师，排除达到日负荷上限者。
3. 代课候选按“同学科、当日剩余容量、当前负荷、教师 ID”稳定排序，最多输出规则指定数量。
4. 若无代课候选，遍历补课时段；补课候选必须同时满足班级空闲、教室容量与开放状态，以及授课教师学科资质、时段可用和日负荷约束。原缺勤教师仅在其声明补课时段可用时参与候选。
5. 每门课输出 `substitute`、`reschedule` 或 `uncovered`，同时给出理由和备选项。
6. 这是独立候选预览，不自动占用资源；多门课程选中同一教师/时段时在组合冲突中提示人工取舍。

## 输出与执行
```bash
python3 scripts/plan_coverage.py --demo --json
python3 scripts/plan_coverage.py --input examples/sample_input.json --out-dir output
python3 scripts/plan_coverage.py --input - --strict < data.json
```
- `coverage_plan.json`：结构化方案、候选项、组合冲突和数据问题，可供教务适配层消费。
- `coverage_plan.md`：受影响课程总表、推荐方案、备选方案、冲突与人工确认清单。
- `--strict` 在存在未覆盖课程、组合冲突或 error 时返回退出码 2；`--json` 只打印不落盘。

## 交互
默认仅生成预览，不写回 SIS/LMS、不发送通知。报告要求人工确认代课资质、教师意愿、工作量口径、教室开放状态和通知范围。修正输入后可重跑；输出目录可直接删除完成撤销。解析失败时返回中文错误且不生成半成品。

## 限制
纯 Python 3 标准库，零依赖、离线运行。所有示例均为模拟数据。暂不处理跨校区通勤时间、连续课最短间隔、法定节假日、薪酬核算和审批流；真实落地需通过适配层接入最新课表、教师资质和教室状态。
