---
name: edu-objective-assessment-checker
displayName: 教学目标-评估一致性诊断
version: 0.1.0
author: ht
type: educational
---

# edu-objective-assessment-checker · 教学目标-评估一致性诊断

## 一、场景定位

面向中小学/高校一线教师、教研员、备课组长，在**备课阶段**（写完单元目标和测验/作业题后）对二者做**事前一致性体检**，避免出现"高阶认知目标但题目全是低阶记忆"、"某些核心目标没有对应考核题"等典型问题。理论基础：Anderson & Krathwohl 修订版布鲁姆分类法 + Wiggins & McTighe 的逆向设计 (Backward Design)。

**与现有 `homework-grading-analyzer` 的关系**: 后者做测后批改+学情诊断；本 Skill 做测前一致性预检，两者形成"诊断—评估"闭环，不重叠。

## 二、触发关键词

当用户提到以下场景时优先使用本 Skill：
- "检查一下我的单元目标和测试题是否对齐"
- "教学目标 vs 试题 覆盖度分析"
- "Bloom 层级匹配检查 / 一致性体检"
- "逆向设计的 backward design 校验"
- "学习产出 OBE 评价矩阵生成"

## 三、输入规范

### 推荐格式：结构化 JSON

```jsonc
{
  "course_name":"高中数学·第3章",          // 可选
  "unit_name":"函数与极限",                // 可选
  "objectives":[                          // 必填
     {"id":"O1","text":"学生能够背诵有理数的定义"},
     {"id":"O2","text":"学生会应用公式求解一元一次方程"}
  ],
  "items":[                               // 必填；字段名也可为 assessments/questions
     {"id":"Q1","points":5,"text":"计算方程 x+5=10 的解"},
     {"id":"Q2",
      "explicit_objective_ids":["O1"],    // 可选：教师显式标注本题考核的目标编号
      "text":"默写出有理数在数轴上的定义和分类表"}
  ]
}
```

字段说明：
| 字段 | 是否必填 | 说明 |
|---|---|---|
| `course_name` | 否 | 课程+章节名 |
| `unit_name` | 否 | 单元名 |
| `objectives[].id` | 自动分配 | 不传则按顺序赋 `O1, O2...` |
| `objectives[].text` | **必填** | 目标描述文本 |
| `items[].points` | 默认1.0 | 分值 |
| `items[].explicit_objective_ids` | 可选 | 显式标注此题关联哪些目标 |

## 四、输出产物（默认写入 `--out-dir` 目录）

| 文件 | 用途 |
|---|---|
| alignment_report.md | 教师可读 Markdown 报告（含覆盖矩阵 + Bloom 分布 + 失配对 + 干预建议）|
| coverage_matrix.csv | 客观题×主观题覆盖矩阵 CSV 格式便于二次分析 |
| summary.json | 结构化摘要便于二次集成到 LMS 或 SIS 系统 |

## 五、CLI 调用方式

```bash
python3 scripts/check_alignment.py \
    --json samples/sample_input.json \
    --bloom data/bloom_verbs.json \
    --out-dir ./output
```

退出码：
- 0 成功
- 2 输入文件不存在
- 3 数据校验失败（JSON 解析错误或必填字段缺失）
- 4 内部异常

## 六、检测规则速查

| 规则 | 触发条件 | 报告呈现方式 |
|---|---|---|
| Bloom 动词识别 | 句中出现预设动词字典中的动词 | 在"目标分布表"显示层级标签 |
| 显式标注匹配 | item.explicit_objective_ids 包含 obj.id | 矩阵中标记 ✓ explicit |
| Bigram 隐式命中 | 两段中文共享 ≥1 个非停用词 bigram | 矩阵中标记 ✓ bigram:`<词>` |
| 未被覆盖目标 | 某个 objective 与所有 items 都无任何 matched 关系 | 列入"未被覆盖的目标"清单 |
| 孤儿题 | 某 item 与所有 objectives 无 matched 关系 | 列入"未关联目标的题目"清单 |
| 高低阶失配 | 高阶(analyze+)目标 ↔ 低阶(<analyze)题目 反之亦然 | 列入"认知层级失配对"+ 给出方向箭头 |
| 综合评分公式 | coverage_rate×40 + avg_match_rate×30 - mismatch_penalty(≤10) - orphan_penalty(≤15) | 总分 0–100 显示于概览区 |

## 七、限制与适用范围

适用场景：
- 单课时或多课时的目标与测验题对齐检查
- 学科不限（基于中英文混合的描述性目标）
- 教研组集体备课时快速发现盲点

已知局限:
- v0.1 仅支持 JSON 输入；自然语言粘贴模式将在下版本提供
- Bloom 分类依赖内置约50个常用中文动词词典，未识别时会标 unknown 但仍参与 bigram 命中判断
- bigram 匹配是粗粒度的语义近似方法，可能出现误判（建议结合 explicit_objective_ids 标注提升精度）

## 八、版本历史

v0.1.0 (2026-08-16)
首次发布。
