# 考后成绩分析助手（exam-score-analyzer）v1.0.0

面向一线教师、年级组长与教务管理人员的**考后成绩智能分析工具**。输入试卷元信息（题目→知识点·满分·题型·难度）+ 学生逐题得分 CSV，自动产出班级总体统计、分数段分布、试卷质量指标（每题得分率/区分度/整卷信度 Cronbach α）、知识点掌握度诊断与薄弱点排序、学生个体画像与预警名单、讲评课建议（重点讲评题 + 分层作业建议）。

与 `exam-blueprint-generator`（命题细目表）、`exam-paper-assembler`（组卷）构成「命题→组卷→考试→分析→讲评」教学闭环的收尾环节。

## 核心场景与目标角色

| 项目 | 说明 |
|---|---|
| 核心场景 | 期中/期末/月考/周测阅卷完成后，把「学生逐题得分明细」交给本工具，几分钟内得到完整考情分析 |
| 目标角色 | 一线教师（讲评备课）、年级组长（班级横向对比）、教务管理人员（命题质量监控） |
| 行业属性 | 基础教育 / 职业教育 / 高校编程类课程，通用计分制考试均可适配 |

## 核心增益（解决痛点）

1. **省时**：均分/及格率/分数段手工统计费时易错 → 一键出全量统计；
2. **科学命题**：每题得分率/区分度 + 整卷信度 Cronbach α → 命题改进有量化依据；
3. **讲评有据**：重点讲评题（得分率低 × 区分度好）自动圈定，不再「凭感觉」；
4. **分层有力**：学生预警名单 + 薄弱知识点排序 → 分层教学/补差有抓手。

## 输入

1. **试卷元信息 JSON**（`--meta`）：`exam`、`course`、`date`、`total_marks`、`className`、`questions[]`（id/marks/kp/type/difficulty），以及可选口径参数 `pass_rate`（及格线，默认 0.60）、`excellent_rate`（默认 0.85）、`low_rate`（默认 0.30）、`group_fraction`（区分度分组比例，默认 0.27）。
2. **学生逐题得分 CSV**（`--scores`）：表头支持中英文别名（`student_id|sid|学号`、`name|姓名`、`class|班级`）；题目列支持 `Q1|q1|t1|题目1` 等，按出现顺序与 meta.questions 对应；缺考=整行留空、某题未答=单元格留空、非数字/超满分=按缺失处理并告警。

## 输出（--out-dir，默认 output/）

| 文件 | 用途 |
|---|---|
| analysis_report.md | 主报告：总体概况/分数段/试卷质量指标/知识点掌握度/学生画像/讲评建议/数据说明 |
| report.html | 自包含可视化报告（无外部依赖，桌面/移动端自适应，可打印） |
| class_summary.csv | 班级汇总指标（Excel 直开，UTF-8 BOM） |
| question_stats.csv | 每题统计（得分率/满分率/区分度/评价） |
| knowledge_stats.csv | 知识点掌握度（含薄弱标记） |
| students.csv | 学生总分/百分位/未答/薄弱知识点/预警 |
| analysis.json | 全量结构化结果（供二次处理） |

## 统计口径（教育测量学常用约定）

- 得分率 P = 题平均分/题满分；P≥0.85 偏易、0.60–0.85 适中、0.40–0.60 偏难、<0.40 过难；
- 区分度 D = 高分组（总分前 27%）与低分组（后 27%）该题得分率之差，有效人数≥6 时计算；
- 信度 Cronbach α = k/(k−1)·(1−Σσᵢ²/σ总²)，需逐题作答的完整样本 ≥4 人；
- 掌握度 = 知识点下实得分合计/(满分合计×实考人数)；<60% 薄弱、≥80% 已掌握。

## 使用方法

```bash
python3 scripts/score_analyzer.py --demo                                # 内置示例数据全流程演示
python3 scripts/score_analyzer.py --meta meta.json --scores scores.csv   # 基本用法
python3 scripts/score_analyzer.py --meta meta.json --scores scores.csv --out-dir out/ --bins 10
python3 scripts/score_analyzer.py --meta meta.json --scores scores.csv --pass-rate 0.5 --excellent-rate 0.8
python3 scripts/score_analyzer.py --meta meta.json --scores scores.csv --strict --no-html
```

退出码：0=成功（含告警）；2=输入错误（文件缺失/格式非法/统计口径冲突）；1=内部异常。

## 安全与可靠

- 零第三方依赖、纯标准库、离线计算、确定性输出（同一输入两次运行结果一致）；
- 无 shell/eval/网络调用；用户可控文本（考试名/课程/学生名/知识点）HTML 转义并截断；
- CSV 输出对所有以 `= + - @` 或制表符开头的单元格加 `'` 前缀（防公式注入）；
- Markdown 表格单元格竖线/控制字符清洗。

## 范围与限制

- 独立本地计算器：成绩取教务系统导出/手工整理的 CSV，未直接对接具体教务系统（适配层留作扩展点）；
- 只做统计与建议生成，不代替教师对教学内容的判断；讲评建议基于规则模板，可结合学科经验再加工；
- 主观题成绩需人工评判给定分（打分请用 homework-grading-analyzer）；
- 样例数据 `examples/` 与 `--demo` 为确定性模拟，供验证与演示。

## 联动

- 上游：`exam-blueprint-generator`（细目表）、`exam-paper-assembler`（组卷）可直接为 meta 提供题目与知识点信息；
- 下游：预警名单/薄弱知识点可直接作为 `student-academic-warning` 预警与分层教学输入。

## 交付清单

```
exam-score-analyzer/
├── SKILL.md                  # 技能定义（front matter + 场景/输入/执行/口径/安全/联动/验证）
├── README.md                 # 本文件（交付说明）
├── scripts/score_analyzer.py # 主程序（v1.0.0，纯标准库）
├── examples/                 # 示例：meta JSON + 得分 CSV + 演示输出
├── demo_output/              # 内置演示真实运行产物（md/html/csv×4/json）
├── tests/
│   ├── run_self_test.sh      # 30 组 CLI 用例 + 15 项内容断言（45/45 通过）
│   └── make_fixtures.py      # 边界/异常/安全夹具生成器
└── docs/
    ├── 自测记录.md           # 30 条测试 Query 记录（expected/actual/结论）
    ├── 效果自评.md           # 准确性/可用性/稳定性/行业适配/风险自评
    └── 大模型教育产品原型日报_2026-08-26.md
```

## 验证结论

自动化自测 `tests/run_self_test.sh`：30 组 CLI 用例 + 15 项内容断言，覆盖常规流程、中文/同义列名、缺考/缺答、边界输入（缺文件/非法 JSON/合计不匹配/越界参数/空表头）、异常数据（非数字/超满分/全缺考/单学生/全满分）、安全（XSS 转义、公式注入防护）、组合交互、产物完整性，**全部通过（45 项断言 100%）**，两次运行结果一致（确定性验证通过）。