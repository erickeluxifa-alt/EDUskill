# 课前备课就绪度审计器

面向教师、教研员和班主任的离线备课检查工具。它把教案或备课笔记转换成结构化审计结果，重点检查五个维度：学习目标、学习活动、评价证据、教学资源、差异化支持，并额外检查目标覆盖与活动时长。

## 快速使用

```bash
python3 scripts/audit.py examples/sample.json --format md
python3 scripts/audit.py --text "目标：理解抽样。活动：小组练习。评价：出口条。资源：讲义。"
```

输入 JSON 可包含 `course`、`lesson`、`duration_minutes`、`objectives`、`activities`、`assessments`、`resources`、`differentiation`。活动和评价对象可使用 `objective_refs` 标注目标编号。

输出包含 JSON 审计结果或 Markdown 预览，默认不写入任何外部系统。该工具只检查备课结构和可审计证据，不判断学科知识的准确性，也不替教师决定是否开课。
