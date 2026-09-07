# 试卷组卷助手 exam-paper-assembler v1.0.0

面向命题教师、教研组、教务处的自动组卷能力：**细目表 × 题库 → 自动选题组卷 → 可打印试卷与组卷报告**。承接每日教育产品系列的 `exam-blueprint-generator`（08-22），把「命题规划」推进到「出卷成稿」。

## 核心场景
- 任课教师按细目表自动生成期中/期末/周测/单元测验卷（学生版 + 教师版含答案）。
- 教研组基于统一题库一键产出平行卷、补考题。
- 教务处 / 命题组批量组卷前检查题库覆盖缺口（知识点 × 题型 × 难度）。

## 能力组成
| 交付物 | 类型 | 说明 |
|---|---|---|
| `scripts/assembler.py` | Skill（Python 零依赖可执行） | 组卷核心：题量分配（最大余数法）、难度匹配选题、自动去重、缺口补齐与阻断、总分校验、Markdown/JSON 渲染 |
| `examples/sample_blueprint.json` | 示例数据 | 100 分细目表（5 知识点 × 5 题型，兼容 exam-blueprint-generator 输出格式） |
| `examples/sample_bank.json` | 示例数据 | 150 题模拟题库（覆盖各知识点/难度/题型） |
| `components/paper-preview.html` | 组件（纯前端，零依赖） | 加载组卷 JSON 渲染试卷；答案解析开关、打印/存 PDF、移动端/桌面自适应、`textContent` 防 XSS |

## 使用方式

### 1. 命令行（推荐）
```bash
python3 scripts/assembler.py --demo
python3 scripts/assembler.py --blueprint examples/sample_blueprint.json --bank examples/sample_bank.json
python3 scripts/assembler.py -b 细目表.json -k 题库.json --format json --out 卷名 --seed 42
python3 scripts/assembler.py -b 细目表.json -k 题库.json --no-answers          # 学生版
python3 scripts/assembler.py -b 细目表.json -k 题库.json --gap-mode warn        # 容错出卷
```

### 2. 前端预览
浏览器打开 `components/paper-preview.html` → 「选择 JSON」加载组卷输出文件，或点击「加载示例」直接查看；「打印 / 存为 PDF」输出纸质卷效果。

## 输入规范
**细目表（JSON）**：`course / exam / total_marks / knowledge_points[{name,weight,level}] / question_types[{name,count,marks,difficulty}] / difficulty_target`——与 exam-blueprint-generator 输出格式一致，可直接串联使用。
**题库（JSON）**：`questions[{id,type,kp,difficulty,marks,stem,options?,answer,explanation?}]`；
- `type`、`kp` 必须与细目表题型/知识点同名；
- `options` 可省略（填空题/简答题）；选项文本可带 `A.` 前缀（自动清理）。

## 输出
- **Markdown 试卷**：学生版（无答案）/ 教师版（含答案+解析）＋试卷头信息；尾部附组卷报告。
- **JSON**（`--format json`）：`{paper:{...,sections:[...]}, report:{gaps,warnings,difficulty_dist,kp_coverage,marks_ok}}`，供预览组件直接加载。
- **组卷报告**：组题数、总分对齐校验、难度分布、知识点覆盖、缺口/补齐告警。

## 核心规则（组卷策略）
1. 知识点题量按权重最大余数法分配；权重全 0 时退化为均分。
2. 难度优先匹配（目标题型难度 → 题库题难度，取最接近者随机）；精确匹配不足时采用次优难度并如实呈现。
3. 每题全网同卷不重复；某知识点缺题时先用同题型同分值未用题目补齐并告警；仍不足则在 strict 模式整体拒绝（列出缺口），warn 模式输出提示继续生成。
4. 总分校验：实际选题总分与 `total_marks` 偏差 > ε 视为未对齐（strict 阻断，warn 标注）。
5. `--seed` 固定随机种子，同输入同输出可复现（试卷版本可控）。

## 依赖与限制
- 依赖：Python 3.10+（仅标准库）；组件无任何网络/第三方依赖。
- 限制：题干不生成内容（需题库有题）；未接真实题库系统（外部系统接入时以适配层 + 模拟数据演示）；题型间分值差异场景未做「题型内跨分值」自动换算（要求同题型单题分值一致）。

## 自测摘要
- 共执行 **24 条自测 Query**（常规 12 / 同义触发 2 / 组合 3 / 边界输入 4 / 异常数据 3），全部通过，典型案例：demo 组卷 36 题总分 100 对齐；缺知识点时 strict 阻断并列出缺口 vs warn 补齐告警；总分冲突阻断；非法 JSON/重复 id/缺字段均友好报错。详见 `自测记录_2026-08-25.md`。
- 组件：HTML 结构解析通过（html.parser），内嵌 JS 通过 `node --check` 语法校验，示例数据 JSON 解析通过；桌面 ≥860px/移动 ≤640px 断点及 `@media print` 已实现（浏览器实际渲染需人工确认）。

## 限制与后续
- 试卷排版为 Markdown 文本渲染，精细化排版（题号自动连续、分页符）不在 v1 范围；`paper-preview.html` 支持打印场景替代。
- 下一步：题目难度系数联动（细目目标难度推导题型难度）、Word（docx）导出、题库批量导入（Excel）、平行卷防重复率约束。