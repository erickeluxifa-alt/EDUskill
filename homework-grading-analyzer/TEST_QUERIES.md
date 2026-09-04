# homework-grading-analyzer 测试查询矩阵

> 共 20 条测试查询，覆盖 正常路径 / 同义触发 / 边界场景 / 异常分支 / 复合任务 五类。
> 执行环境：Python 3.x + 标准库；样本数据见 [`samples/`](./samples/)。

## 一、正常路径（Happy Path）·6 条

| # | 查询 | 预期行为 | 验证点 |
|---|---|---|---|
| H1 | "用 samples/answer_key.json 和 samples/student_responses.csv 跑一次批改" | exit=0, 输出4个文件 | grading_summary.md 含班级概览/分层/逐题热力图 |
| H2 | "帮我把这次测验批量批改一下并生成学情报告" | 同上 | dashboard.html 可在浏览器打开且无破损标签 |
| H3 | "分析一下全班哪些知识点薄弱" | weak_kps 字段非空 | summary.json 中包含至少1个weak_kp |
| H4 | "给每个学生生成分层干预建议" | student_grades.csv advice 列非空 | 至少3种不同advice文本出现 |
| H5 | "导出学生成绩 CSV" | student_grades.csv 文件存在且首行匹配表头约定 | 表头含student_id,name,score_pct,tier等列 |
| H6 | "--out-dir 参数指定到/tmp/hga_test2 时应创建目录" | 目录被自动 mkdir parents=True 创建 | 无 PermissionError 抛出 |

## 二、同义表述（Synonym Triggers）·5 条

| # | 查询 | 应能识别意图的场景假设(助手侧) |
|---|---|---|
| S1 | "改卷子" | 触发本Skill而非其他无关技能 |
| S2 | "我有答案和学生作答CSV生成一份学情分析报告吧" | 识别为本 skill 调用 CLI 模式 |
| S3 | "统计一下班级分数分布和及格率" | 命中render_md中分层分布章节逻辑 |
| S4 | "看看谁需要重点关注辅导" | 对应HTML看板中的需关注学生清单表格渲染 |
| S5 | "把每道题做错的人数汇总一下" | per_question_stats.wrong_rate字段输出 |

## 三、边界场景（Boundary Cases）·4 条

| # | 场景构造 | 预期结果 |
|---|---|---|
| B1 | 全角字符作答：Q1填`Ｄ`而非`D`, Q3填`t`(小写)而非`T` | 经norm()归一化后判为正确，得分率100% |
| B2 | 多选题部分对：正确ACD，学生答AD(子集)→0.5分;学生答ABCD(超集含错选B)→0分 | gr_mc按集合关系返回不同值 |
| B3 | numeric题容差：answer=5.00 tolerance=.05 学生答4.96或5.04均判定满分; 答4.94则0分 | gr_num使用abs差比较tolerance阈值 |
| B4 | fill_blank partial credit: keywords=["x","y","二元"] pratio=.33 答案"x=4,y=9 二元一次方程组解出"命中全部关键词 → rt=1.0 返回 .8 区间满分附近分值 | gr_fb走partial分支返回 round(rt*.5+.3,4)=.8 |

## 四、异常分支（Error Branches）·3 条

| # | 异常输入 | 预期退出码 & 错误消息关键片段 |
|---|---|---|
| E1 | --key 指向不存在的文件路径 `/nonexistent.json` | exit code = 2 ; stderr 包含 "[ERROR] 输入文件不存在："|
| E2 | answer_key JSON 缺失 questions 字段 或 questions=[] | exit code = 3 ; stderr 提示 "questions 为空" |
| E3 | answer_key JSON 内有重复题号 id:1 出现两次 | exit code = 3 ; stderr 提示 "题号重复:1" |

## 五、复合任务场景（Composite Workflows）·2 条

| # | 任务描述 | 关键链路验证 |
|---|---|---|
| C1 | 教师上传问卷星导出的xlsx先转csv再批改 | 由上层先用 xlsx skill 转格式再调本脚本--csv参数; 本层只负责接收合法csv执行处理。已验证支持utf-8-sig BOM头自动剥离. |
| C2 | 多次测验累积对比时复用同一份key_meta.title作为标识符进行后续聚合 | 本次产物summary.json内嵌title/date/n_questions等元数据便于下游系统拼接历史趋势 |

---

## 实际自测运行记录摘要

```bash
$ python3 scripts/analyze_homework.py \
    --key samples/answer_key.json \
    --csv samples/student_responses.csv \
    --out-dir /tmp/hga_test
[OK] Markdown 报告已生成 → /tmp/hga_test/grading_summary.md
[OK] 学生成绩 CSV 已导出 → /tmp/hga_test/student_grades.csv
[OK] 可视化看板已构建 → /tmp/hga_test/dashboard.html
[OK] 结构化 JSON 摘要已写出 → /tmp/hga_test/summary.json
```

抽样校验：
- class_size = 10 ✓ 与CSV行数一致
- average ≈ 47% ✓ 符合手工估算
- tier_counts {A:0,B:3,C:1,D:6} ✓ 分层规则生效
- weak_kps 列表包含5个知识点 ✓ 掌握度<60%筛选生效
- S001张明 score_pct=89.33% tier=B advice提及应用题建模薄弱 ✓ 个案干预建议准确

异常分支E1实测：
```
[ERROR] 输入文件不存在：/nonexistent.json
EXIT=2
```
符合预期。

## 待补完测试项 (Roadmap v0.2+)
- [ ] 大规模压力测试 (>500名学生)
- [ ] Excel xlsx 直接输入支持(当前依赖外部转换工具如xlsx skill)
- [ ] LLM语义级简答评分集成后的回归测试套件
- [ ] HTML报告可交互性前端单元测试(Selenium/Cypress级别)

