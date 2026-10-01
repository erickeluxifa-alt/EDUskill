# 课堂互动证据诊断

面向教师、班主任和教研员的形成性教学辅助 Skill。输入一节课或一周课堂互动的 JSON 汇总，离线输出证据覆盖、参与层级、证据缺口、下一节课干预建议与待确认跟进队列。

## 快速开始

```bash
python3 scripts/diagnose.py --pretty < examples/sample.json
sh tests/run_self_test.sh
```

## 输入输出

输入字段支持 `sessions` 或 `students` 数组。每条记录包含 `name`、`student_id`，可选 `attendance` 以及 `speak`、`question`、`submission`、`collaboration`。输出 JSON 包含 `summary`、`students`、`intervention_plan`、`review_queue`、`side_effects`。

## 适用范围与限制

适用于中小学、高校、职业教育和企业培训中的小班/大班形成性观察。示例数据为模拟数据；无 LMS/SIS 接口、无消息发送、无成绩写回。结果仅表示“目前观察到的证据”，不能作为学生能力、态度、处分或正式预警依据，建议合并至少 3 次课再看趋势。
