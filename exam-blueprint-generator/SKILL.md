---
name: exam-blueprint-generator
displayName: 考试双向细目表生成器
description: 面向课程教师、命题组和教研组的考试命题规划工具。何时使用：需要根据课程知识点及权重、题型和单题分值、难度目标自动生成考试双向细目表（知识点×题型分值矩阵），并校验总分对齐、难度分布和认知层次覆盖时使用。
version: 1.0.0
author: ht
trigger:
  - 生成考试双向细目表
  - 帮我设计试卷分值分配
  - 命题规划 / 出题蓝图
  - 检查知识点分值覆盖
  - 制定难度分层方案
---

# 考试双向细目表生成器

## 目标
面向课程教师、命题组、教研组的命题规划工具：输入考试知识点（权重、认知层次）、题型（题数、单题分值、难度标签），自动生成「知识点 × 题型」分值双向矩阵，并校验总分对齐、知识点覆盖、难度分布与认知层次分布，产出可直接提交教研审查的 Markdown 报告和结构化 JSON/CSV。

## 输入
JSON 文件，顶层包含：

```json
{
  "course": "Python程序设计",
  "exam": "2026年春季学期期末考试",
  "total_marks": 100,
  "knowledge_points": [
    {"name": "基础语法", "weight": 0.2, "level": "了解"}
  ],
  "question_types": [
    {"name": "单项选择题", "count": 10, "marks": 2, "difficulty": "易"}
  ],
  "difficulty_target": {"易": 0.3, "中": 0.5, "难": 0.2}
}
```

字段说明：
- `knowledge_points[].weight`：知识点权重，可为 0（表示权重未知按平均分配），可省略；
- `knowledge_points[].level`：认知层次，取「了解/理解/应用/分析/综合/评价」，缺省「了解」；
- `question_types[].difficulty`：难度标签「易/中/难/混合」，混合表示按难度目标拆解，缺省「混合」；
- `question_types[].level`：题型认知层次，缺省「理解」；
- `difficulty_target`：难度占比，缺省 3:5:2。

## 执行

```bash
python3 scripts/exam_blueprint.py examples/sample_blueprint.json
python3 scripts/exam_blueprint.py input.json --out report.md
python3 scripts/exam_blueprint.py input.json --json --csv
python3 scripts/exam_blueprint.py --demo       # 内置示例
```

## 输出
Markdown 报告（默认 stdout，可用 `--out` 存文件），包含：
1. 知识点 × 题型分值矩阵（行列合计与总分严格对齐）；
2. 题型统计（题数、单题分值、小计、占比、难度、认知层次）；
3. 难度分布汇总（易/中/难，与目标对比）；
4. 认知层次（布鲁姆六层）分值分布；
5. 校验结论：✓ 总分对齐 / ✗ 题型分值不等于满分 / 知识点零分配 / 难度偏差预警 / 高阶层次缺失。

`--json` 输出结构化结果（含矩阵、各知识点分配分值），`--csv` 输出矩阵明细，便于 Excel 处理。

## 规则与边界
- 行列合计与满分严格对齐（0.5 分粒度，最大余数法+整数修正）。
- 输入只读，不修改教师既有命题数据；生成值为命题建议，最终由教研组审定。
- 用户可控文本（课程名、知识点名、题型名）输出前做 HTML 转义和长度截断（200 字符），避免注入。
- 零依赖 Python 标准库实现，无需网络调用，纯本地运行。

## 安全
脚本使用本地 JSON 输入与 `html.escape` 转义后渲染，无 shell 调用、无 eval、无网络请求，示例均为模拟数据。