---
name: homework-grading-analyzer
displayName: 批量批改与学情诊断
version: 0.1.0
author: ht
type: educational
---

# homework-grading-analyzer · 批量批改与学情诊断

## 一、场景定位
面向中小学/高校一线教师、教研员、年级组长，在随堂测验、单元测验或月考后，**批量批改客观题+半结构化主观题，并自动产出班级学情诊断报告**。解决痛点：
1. 教师手工逐题逐人改卷耗时巨大；
2. 选择题能机读但填空/简答仍需人工判分；
3. 即使有分数也缺乏"知识点掌握度"、"分层干预建议"、"班级共性错题清单"等结构化诊断。

## 二、触发关键词
当用户提到以下场景时优先使用本 Skill：
- "帮我把这次测验批量批改一下"
- "我有答案和学生作答 CSV，生成一份学情分析报告"
- "分析一下全班哪些知识点薄弱"
- "给每个学生生成分层干预建议"
- "导出学生成绩 Excel / CSV"

## 三、输入规范

### 3.1 答案 JSON (`answer_key.json`)
```jsonc
{
  "title": "六年级数学·第3单元",
  "subject": "数学",
  "date": "2026-08-14",
  "questions": [
    {"id":1,"type":"single_choice","points":4,"knowledge_point":"有理数",
     "options":{"A":"..."},"answer":"D"},
    {"id":2,"type":"multi_choice","points":5,"knowledge_point":"几何",
     "answer":"ACD"},
    {"id":3,"type":"true_false","points":3,"knowledge_point":"代数运算",
     "answer":"T"},
    {"id":4,"type":"fill_blank","points":5,"knowledge_point":"方程",
     "accepted_answers":["4"],"allow_partial_credit":false},
    {"id":5,"type":"numeric","points":5,"knowledge_point":"计算能力",
     "answer":"5.00","tolerance":0.05},
    {"id":6,"type":"short_answer","points":8,"knowledge_point":"应用题建模",
     "partial_keywords":["x=4","y=9","二元一次"]}
  ]
}
```

### 3.2 学生作答 CSV (`student_responses.csv`)
首行表头支持中英文别名：`student_id|sid|学号` 任选其一；`name|姓名`任选其一；题目列名 `q{N}|Q{N}|question_{N}|t{N}` 或直接题号。
示例：
```
student_id,name,Q1,Q2,Q3,Q4,Q5,Q6
S001,张明,D,ACD,T,4,5.00,"设x本笔记本,y支铅笔..."
```

## 四、输出产物（默认写入 `--out-dir` 目录）
| 文件 | 用途 |
|---|---|
| grading_summary.md | 班级概览 + 分层分布 + 逐题热力图 + 知识点矩阵 + 重点学生干预建议 |
| student_grades.csv | 每位学生的得分率/分层/薄弱知识点/建议 |
| dashboard.html | 可视化看板：KPI 卡片 + 条形图分层 + 题目正确率条形图 + 学生关注列表 |
| summary.json | 结构化摘要便于二次集成 |

## 五、CLI 调用方式
```bash
python scripts/analyze_homework.py \
  --key samples/answer_key.json \
  --csv samples/student_responses.csv \
  --out-dir ./output
```

## 六、评分规则速查
| 类型 | 规则 | 半对分值 |
|---|---|---|
| single_choice / true_false | 全角→半角归一化后精确匹配 | 无 |
| multi_choice | 子集完全匹配=满分；选对部分且无错选=50% | 50% |
| fill_blank | 命中 accepted_answers 列表中任意一项即满分；allow_partial_credit=true 时按 partial_keywords 命中比例给 .3~.8 区间分数 | 渐进式 |
| numeric | 数值差 ≤ tolerance 即满分（默认 tolerance = abs(expected)*1% ） | 无 |
| short_answer | 命中 accepted_answers 中关键词得满分；按 partial_keywords 命中率给 .15~.95 分数 | 关键词加权 |

## 七、错误处理约定
- 输入文件不存在 → exit code 2 并打印缺失文件路径
- JSON 解析失败 / questions 为空 → exit code 3 提示数据校验失败原因
- 其他运行时异常 → exit code 1 打印异常类型和消息
