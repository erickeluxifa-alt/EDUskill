# 学生考勤缺勤跟进计划器

## 核心场景

把课程考勤 JSON 转成班主任/辅导员可审核的跟进队列，支持重复缺勤、连续缺勤和迟到累积的确定性统计。

## 运行

```bash
python3 scripts/plan_followups.py examples/sample_input.json --out-dir output
python3 scripts/plan_followups.py examples/sample_input.json --json
```

## 输入输出

输入包含课程、班级和 records；输出 `followup_plan.json` 与 `followup_plan.md`。工具只读本地输入，采用 Python 标准库，不连接 LMS/SIS，不发送消息。

## 限制

连续缺勤依据输入日期排序近似，不代表真实校历；结果是人工跟进优先级，不是纪律或心理风险结论。实际联系、隐私授权、转介和系统写回必须由负责人确认。
