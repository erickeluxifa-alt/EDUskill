---
name: exam-review-planner
displayName: 考后讲评备课助手
description: 面向一线教师、年级组长与教务管理人员的考后讲评课备课工具。输入考试逐题统计（可直接复用 exam-score-analyzer 输出的 analysis.json，或提供逐题统计 CSV/JSON），自动把题目按得分率分为必讲（P<50%）/应讲（50%≤P<85%）/略讲（P≥85%），按「紧迫度加权 + 区分度」分配精讲时长，产出讲评课教学方案（时间轴、核心题单、略讲题清单、变式建议）、分层辅导名单（A/B/C 层）、自包含 HTML 讲评课件（桌面/移动端自适应、可打印）、结构化 JSON 与 CSV（Excel 直开）。何时使用：期中考/期末考/月考/周测阅卷完成后需要快速产出讲评课备课方案与分层辅导名单时；与 exam-blueprint-generator、exam-paper-assembler、exam-score-analyzer 构成「命题→组卷→考试→分析→讲评」闭环。
version: 1.0.0
author: ht
trigger:
  - 讲评课怎么上 / 考后讲评方案
  - 哪些题必讲哪些略讲
  - 帮我生成讲评课件
  - 分层辅导名单怎么分
  - 讲评时间轴怎么排
  - 明天要讲评，帮我备一下课
---
# 考后讲评备课助手（exam-review-planner v1.0.0）

## 场景定位
老师阅卷拿到成绩后，最耗精力的不是「讲」，而是「**决定讲什么、讲多久、给谁补**」。本工具一台命令把逐题统计转成可直接上课的方案：
**必讲/应讲/略讲分级 → 精讲时长分配 → 时间轴 → 变式建议 → A/B/C 分层辅导名单**，输出 Markdown 教案、HTML 课件与 CSV 名单（Excel 直开）。

解决痛点：
1. 讲评题「凭感觉」选、时长随意，重点题讲不透、简单题耗时间；
2. 分层辅导靠手工排序成绩单，A/B/C 名单整理费时；
3. 变式题无出处，讲完没有当堂训练；
4. 备课产出散落（教案、课件、名单各做各的），无法复用前置分析结果。

## 输入（三选一，必填）
| 参数 | 说明 |
|---|---|
| `--analysis PATH` | 直接复用 `exam-score-analyzer` 输出的 analysis.json（推荐，联动闭环） |
| `--qstats PATH` | 逐题统计 CSV 或 JSON 数组（题号/知识点/满分/得分率/区分度/题型/题干） |
| `--demo` | 内置示例数据（8 题 + 16 名学生）跑通全流程 |

可选参数：`--students PATH`（成绩单 CSV，**优先级最高**，覆盖内置名单）、`--exam/--course/--class-name/--date`（元信息）、`--total-marks/--pass-rate/--excellent-rate/--low-rate`（分层口径）、`--session 45`（讲评课时长）、`--out-dir`、`--no-html/--no-md`（产物裁剪）、`--quiet`。

列名/键名支持中英文别名（题号|id|qid、得分率|正确率|p|avg 等），大小写不敏感，缺列自动降级并给出告警——成绩单、逐题导出「拿来就能用」。

## 执行
```bash
python3 scripts/review_planner.py --demo --out-dir out/                        # 全流程演示
python3 scripts/review_planner.py --analysis ../exam-score-analyzer/analysis.json --session 45
python3 scripts/review_planner.py --qstats qstats.csv --students roster.csv --exam 初二期中
python3 scripts/review_planner.py --analysis a.json --students s.csv --no-html --out-dir out/
```

## 输出（--out-dir）
| 文件 | 用途 |
|---|---|
| review_plan.md | 讲评课教学方案（总体反馈/时间轴/核心题单/略讲清单/变式/分层/跟踪） |
| review_deck.html | 自包含讲评课件（无外部依赖，桌面/移动自适应，可打印） |
| review_plan.json | 全量结构化方案（供前端组件/二次处理） |
| question_cards.csv | 每题卡片（含分类/讲法/精讲时长/变式建议，Excel 直开） |
| tier_students.csv | A/B/C 分层辅导名单（含总分与建议任务） |

退出码：0=成功（含告警）；2=输入错误（缺文件/格式非法/题目统计为空等）；1=内部异常。

## 分级与时长口径
- 得分率 P 分档：P<50% **必讲**（精讲）、50%≤P<85% **应讲**（精讲）、P≥85% **略讲**（小组自查+口头点易错）；
- 讲法：区分度 D≥0.3 按「讲思路」，否则「全班统一讲概念」；
- 精讲时长：按紧迫度权重 0.6×(1−P)+0.4×D 分配总预算，单题上限 7 分钟；预算随 `-session` 线性放大/压缩；
- 时间轴：时长≥15 分钟时「阶段反馈→自查自纠→核心讲评→变式训练→分层辅导→收尾作业」6 阶段；<15 分钟降级为「总体反馈→核心→收尾」3 阶段；
- 分层 A/B/C：按满分与 优秀线/及格线（默认 85%/60%，可配置）划层，C 层附「结对帮扶+精讲题重做」任务与优先知识点；
- 全员高分（无必讲/应讲）时自动切换为#拔高引导题#，不空转。

## 安全边界
- 零第三方依赖、纯标准库、离线计算、确定性输出（相同输入两次运行结果一致，自测 T26 有哈希校验）；
- 无 shell/eval/`写入系统目录之外的文件仅限 --out-dir`；
- 用户可控文本（考试名/课程名/知识点/题干/学生名/变式建议）：
  - HTML 课件全部 `html.escape` 转义并截断 100 字符（XSS 测试通过）；
  - Markdown 单元清洗：竖线→全角、`<`/`>`→全角、换行/控制字符清除（可执行文本不落地）；
  - CSV 对所有以 `= + - @` 或制表符开头的单元格加 `'` 前缀（防 Excel 公式注入）。

## 限制与适配
- 当前为独立本地计算器：输入取自教务系统导出或手工整理的文件，未直接对接具体系统（适配层留作扩展点）；
- 规则型建议（时长/分层/讲法）基于教育测量常用约定，仍需教师结合学科经验把关；
- 不讲「怎么教」，只讲「教什么、讲多久、给谁补、怎么练」的备课骨架；
- `examples/` 与 `--demo` 为确定性模拟样例，供验证与演示。

## 联动
- 上游 `exam-score-analyzer`：analysis.json 直接作为 --analysis 输入（闭环第 4 环）；
- 上游 `exam-paper-assembler`：组卷的题目清单可经 --qstats 复用；
- 检索 `exam-blueprint-generator` 细目表可补齐未标注知识点。

## 验证
`tests/run_self_test.py`（python3 直接跑）：30 条 CLI 用例 + 断言，全部通过（100%），覆盖常规主线、同义/别名/降级、组合覆盖、缺输入/坏文件、边界（全高分/全错/单题/无知识点/5 分钟课时）、异常数据（越界/非法/跳过）、确定性（两次哈希一致）、安全（XSS 双通道、公式注入、产物裁剪）。