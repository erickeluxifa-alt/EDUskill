---
name: student-academic-warning
display_name: 学生学业预警分析工具
description: 多维度学情风险评分与预警分级工具，用于教务管理者对学生学业数据进行批量风险评估和分级预警。
version: "1.0.0"
author: ht
---

# Student Academic Early Warning Analyzer | 学生学业预警分析工具

## 概述

本 Skill 用于教务管理者、辅导员和院系负责人对学生学业数据进行批量多维度风险评分和分级，输出可操作的干预建议清单。

**触发方式**: 当用户提到以下场景时自动匹配：
- 学业预警分析、学生风险评分、学情诊断、挂科统计、出勤率预警、学分进度检查、干预建议生成、退学风险识别等。

## 能力说明

**输入**：JSON 格式的学生列表（支持文件路径或 STDIN），包含学号、姓名、年级、专业、GPA、挂科门数/学分、应修/已修学分、考勤数据、违纪次数和心理标记等字段。可选 `config_overrides` 自定义阈值参数。

**处理逻辑（7 维度风险评分引擎）**：
| 维度 | 触发条件 | 分值 |
|------|---------|------|
| GPA 成绩 | <2.0 或 <2.5 | 30~50 或 15 |
| 挂科门数 | ≥1 门 | 12分/门，上限60 |
| 挂科学分比例 | 占应修>15% | 20~50 |
| 出勤率 | <75%或<85% | 25~65 或10 |
| 学分进度滞后 | 进度低于预期≥20% | 18~48 |
| 违纪处分 | 每次 | 8 |
| 心理标记 | 布尔标志 | 5 |

**输出**：
- JSON 格式完整报告（含每个学生的风险评估详情）
- 统计摘要（各层级人数分布、待干预优先级排序表）
- 干预建议列表（基于级别与具体维度组合生成）

## 使用方法

```bash
# 文件输入
python3 scripts/academic_warning_analyzer.py --input examples/sample_students.json

# 输出到指定文件
python3 scripts/academic_warning_analyzer.py --input examples/sample_students.json --output report.json

# 从 stdin 读取
echo '{"students":[...]}' | python3 scripts/academic_warning_analyzer.py --stdin

# 显示帮助
python3 scripts/academic_warning_analyzer.py --help
```

## 版本信息

* version: v1.0.0 · 发布日期 2026-08-18󠅣󠅤󠄷󠄹󠄱󠅣󠄸󠄴󠄶󠅤󠄳󠄲󠅦󠅥󠅦󠄵󠅡󠄷󠄸󠅢󠄷󠅦󠅦󠄷󠄲󠄵󠅢󠅥󠅡󠅢󠅤󠄶
