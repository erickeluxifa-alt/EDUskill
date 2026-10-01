# homework-grading-analyzer 使用说明

> 教育场景原型 · 第 03 号 · 发布日期 2026-08-14

## 这是什么？
一个面向一线教师的 **批量作业自动批改 + 学情诊断工具**。教师只需准备两份文件：
1. 标准答案 JSON（含题型、知识点归属、可接受答案）
2. 学生作答 CSV（一行一名学生）

即可一键获得 Markdown 报告、CSV 成绩单、HTML 可视化看板三件套，并附带每名学生个性化干预建议。

## 快速开始

### Step 1 准备标准答案
参考 [`samples/answer_key.json`](./samples/answer_key.json)，必填字段：
- `id` — 题号（整数）
- `type` — 支持 `single_choice` / `multi_choice` / `true_false` / `fill_blank` / `numeric` / `short_answer`
- `points` — 该题满分值
- `knowledge_point` — 所属知识点名称
- `answer` 或 `accepted_answers` 或 `partial_keywords`

### Step 2 导出学生作答 CSV
推荐使用问卷星 / 腾讯文档 / WPS 表格导出 UTF-8 编码 CSV。第一行需包含：
- 学号列：`student_id` 或 `sid` 或 `学号`
- 姓名列：`name` 或 `姓名`
- 各题列：`q1`, `Q1`, `question_1`, 数字编号 或 `t1` 都会被识别

空白单元格视为未作答。多选题用连写字母如 `ACD`，无需分隔符。

### Step 3 运行脚本
```bash
python3 scripts/analyze_homework.py \
  --key your_answer_key.json \
  --csv your_students.csv \
  --out-dir reports/
```
成功后会在 `reports/` 下看到四个产物文件。

## 实际样例演示
项目内置了一份小学六年级数学测验的样本数据（10 名学生 × 6 题），可直接体验：

```bash
python3 scripts/analyze_homework.py \
  --key samples/answer_key.json \
  --csv samples/student_responses.csv \
  --out-dir /tmp/demo_output && open /tmp/demo_output/dashboard.html
```

预期结果摘要：
- 班级平均得分率 ≈ 47%
- 及格率约 40%（A:0 B:3 C:1 D:6）
- 自动识别出 Q2 多选题和 Q6 应用题为全班难点
- 对 D 层学生给出针对性干预提示

## 设计要点说明
1. **全角字符兼容**: 自动将 ＡＢＣＤ / 全角数字转换为 ASCII 后再比对，避免格式差异误判;
2. **多列别名识别**: 表头命名灵活，方便对接不同问卷平台导出格式;
3. **渐进式给分机制**: 主观题不简单二分，而是根据关键步骤词命中率给予梯度反馈;
4. **分层规则固定为 A/B/C/D 四档**, 与国内常见教学评估口径一致:
   - A ≥90%, B [75%,90%), , C [60%,75%), , D <60%

## 已知限制 (Prototype v0.1)
- 不处理图片附件类答题(纯文本判定);
- 未接入 LLM 进行语义级简答评分，仅基于关键词命中;
- 中文标点变体不做深度清洗(逗号句号等);
- HTML 报告不含交互筛选功能;

## 测试覆盖情况
详见 [`TEST_QUERIES.md`](./TEST_QUERIES.md) 共编排 ~20 条查询覆盖正常路径 / 同义表述 / 边界场景 / 异常分支四类情形。

## 反馈渠道
欢迎在 GitHub Issues 中提出改进意见！
