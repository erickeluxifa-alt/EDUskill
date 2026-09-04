---
name: exam-followup-reviewer
displayName: 考后教学复盘助手
description: 考后教学复盘与命题回流助手。输入 exam-score-analyzer 产出的 analysis.json（单班或多班），自动输出班级画像、共性薄弱知识点归因、命题质量四象限判定与回流建议（blueprint_feedback.json 可直接供 exam-blueprint-generator 下一轮命题参考）、学生帮扶名单，并生成 Markdown / 单文件 HTML 复盘报告。何时使用：考后需要 5 分钟拿到一份「班级画像 + 知识点归因 + 题目质量 + 帮扶名单」的完整复盘，或需要把考试结果回流到下一轮命题时使用。
version: 1.0.0
author: ht
trigger: 考后复盘、考试分析报告、试卷质量分析、知识点薄弱归因、命题质量回流、帮扶名单（也可在当前阶段 step 中明确要求时触发）
---

# 考后教学复盘助手（exam-followup-reviewer）

## 一、场景与定位

考试结束后，任课教师/教研组需要回答三个问题：**考得怎么样？薄弱在哪？下一轮怎么改？**
本技能直接消费 `exam-score-analyzer` 输出的 `analysis.json`（无需手工整理数据），一条命令产出：

1. **班级整体画像**：均分、及格率/优秀率/低分率、得分率、信度 α、画像档位（优秀/良好/中等/待提升/需重点改进）
2. **知识点掌握度**：逐知识点得分率 + 掌握度档位 + **多班共性薄弱归因**（≥2 班得分率<60% 的知识点自动标为共性薄弱并给改进动作）
3. **命题质量与回流建议**：每题四象限判定（双低·疑议题 / 高区分·拉分题 / 送分·低效题 / 正常）+ 难度建议，写入 `blueprint_feedback.json`，**与 exam-blueprint-generator 的输入格式对齐，可直接回流下一轮命题**
4. **学生帮扶清单**：按名次尾部/预警高危/百分位低三重标记自动圈定名单，可导出 CSV 供班主任/辅导员跟进

## 二、能力清单

| 能力 | 说明 |
|---|---|
| 单班分析 | `--analysis classA_analysis.json`，产出该班完整复盘报告 |
| 多班横评 | 传多个 `--analysis`：跨班对比画像、共性薄弱归因、题级班级归属 |
| 目录扫描 | `--dir <目录>`：批量扫描目录下所有 analysis.json（自动跳过非 analysis 目录） |
| 可视化报告 | 单文件 HTML（无 CDN/JS 框架，可离线打开、可打印存档） |
| 结构回流 | `blueprint_feedback.json`：知识点难度建议 + 题目双低/拉分清单，供命题环节回归 |
| 数据导出 | class_compare.csv / kp_matrix.csv / help_list.csv（UTF-8-BOM，Excel 直接打开不乱码） |

## 3. 输入格式（analysis.json）

来自 `exam-score-analyzer` 输出，关键字段：

```json
{
  "meta": {"exam": "期中考试", "course": "Python 程序设计基础", "class_name": "计科2401", "questions": [...], "kps": ["基础语法", ...]},
  "totals": {"mean": 68.8, "pass_rate": 0.64, "excel_rate": 0.21, "low_rate": 0.04, "p_overall": 0.71},
  "questions": [{"id": "1", "kp": "基础语法", "marks": 5, "mean": 4.5, "p": 0.9, "d": 0.3}],
  "students": [{"name": "张三", "sid": "201101", "total": 92.0, "pct": 96.0, "tier": "优秀"}],
  "alpha": 0.82, "n_present": 24, "n_total": 25
}
```

- `students` 缺失或为空时：跳过帮扶清单（报告给出提示），其余分析照常
- `meta.questions` 缺失 → 拒绝执行（退出码 2），避免无题目维度数据下产出误导性结论
- 非 JSON / 文件不存在 → 退出码 2；内部异常 → 退出码 1

## 4. 统计口径

- **画像 score = 0.5×得分率 + 0.3×及格率 + 0.2×(1−低分率)**；档位：优秀≥0.85 / 良好≥0.72 / 中等≥0.60 / 待提升≥0.48 / 其余需重点改进
- **知识点掌握度**：已掌握≥80% / 掌握一般≥60% / 薄弱≥40% / <40% 严重薄弱；样本不足判「数据不足」
- **共性薄弱**：≥2 个班级的知识点得分率均 <60%
- **题目四象限**：双低·题证题（p<0.5 且 d<0.2）/ 高区分·拉分题（p<0.5 且 d≥0.3）/ 送分·低效题（p≥0.8 且 d<0.2）/ 正常
- **回流建议**：p<0.4 下调难度 / p<0.6 控制难度 / p≥0.8 可加码 / 其余维持
- **帮扶标记**：尾部25%（名次位置>0.75）+ tier 预警/高危 + 百分位低（超越率≤25%）

## 5. 使用示例

```bash
# 单班
python3 scripts/followup_reviewer.py --analysis examples/classA_analysis.json --out-dir out_a

# 双班横评（同时给回流建议）
python3 scripts/followup_reviewer.py --analysis examples/classA_analysis.json --analysis examples/classB_analysis.json --out-dir out_ab

# 目录批量
python3 scripts/followup_reviewer.py --dir analyses/ --out-dir out_all

# 演示数据（无输入即可跑）
python3 scripts/followup_reviewer.py --demo --out-dir out_demo

# 开关：--no-html / --no-md / --quiet
```

## 6. 输出物（7 个）

| 文件 | 说明 |
|---|---|
| `followup_review.md` | 复盘报告（Markdown，含四节：画像/知识点/命题/帮扶） |
| `followup_report.html` | 单文件可视化报告 |
| `class_compare.csv` | 班级画像对比 |
| `kp_matrix.csv` | 知识点得分率矩阵 |
| `help_list.csv` | 帮扶名单（Excel 可直接打开） |
| `blueprint_feedback.json` | **回流建议**（难度/权重/疑题清单） |
| `followup_summary.json` | 指标摘要（确定性输出，可做 hash 校验/自动读取） |

## 7. 安全边界

- 纯 Python 标准库，无第三方依赖、无网络、无外部文件写入
- 所有输入文本经 HTML 转义（防 XSS）；Markdown 单元格做 `& < > |` 清洗；CSV 防公式注入（`= + - @` 前加 `'`）
- 结果确定性：同输入同输出，可 diff / 校验

## 8. 与 exam 五环的联动

```
exam-blueprint-generator（命题规划）→ exam-paper-assembler（组卷）→ exam（考试）→ exam-score-analyzer（成绩分析）
        ↑
        └──── exam-followup-reviewer（复盘反向回流 blueprint_feedback.json）
```

`blueprint_feedback.json` 的 `kp_feedback[].suggest`（下调难度/控制难度/维持/可加码）与 `question_review[].quad`（疑题清单）为调研对齐格式，exam-blueprint-generator 可直接消费调整下一轮双向细目表。

## 8. 验证

自测脚本 `tests/run_self_test.sh`：31 条断言，覆盖正常流程（demo 双班横评/单班/目录扫描）、异常输入（退出码 2）、空学生容错、XSS/公式注入安全、输出确定性、参数开关，全绿 `PASS=31 FAIL=0`。