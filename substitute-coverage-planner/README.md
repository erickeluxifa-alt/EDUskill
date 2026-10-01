# 教师缺勤代课与调课方案生成

## 核心场景
教师临时请假后，为受影响课程生成同学科代课候选；没有可行代课时生成同时满足班级、教室和授课教师约束的补课候选，并集中揭示资源冲突。

## 目标角色与行业属性
- 角色：教务处、院系教学秘书、年级组长、班主任。
- 行业属性：教育教务排程、课程连续性保障、教师与教室资源协同。
- 可复用范围：高校、职校、中小学；也可作为 SIS/LMS 的离线预检模块。

## 核心增益
把“逐个问教师—查课表—找教室—检查班级冲突”的人工 SOP 固化为可复核规则；结构化 JSON 可直接进入页面、审批流或系统适配层。

## 快速开始
```bash
python3 scripts/plan_coverage.py --demo --json
python3 scripts/plan_coverage.py --input examples/sample_input.json --out-dir output
python3 scripts/plan_coverage.py --input examples/sample_input.json --strict
```

## 输入与输出
输入 JSON 包含缺勤课程、候选教师、教室、班级忙闲、补课时段和可选规则。输出 `coverage_plan.json` 与 `coverage_plan.md`；标准输出模式适合管道组合。

## 依赖与配置
仅依赖 Python 3 标准库，不联网。时段采用 `Mon-1` 格式；可通过 `rules.max_candidates` 控制每课候选数，通过 `rules.allow_cross_subject` 允许跨学科候选（默认关闭）。

## 交付物料
- `SKILL.md`：触发、输入输出、规则、交互和限制。
- `scripts/plan_coverage.py`：排程与报告生成器。
- `examples/sample_input.json`：模拟工作流样例。
- `tests/test_plan_coverage.py`：自动化单元与端到端测试。
- `tests/test_queries.md`：24 条自然语言 Query 验收矩阵。

## 限制
结果仅为候选预览，不占用教师或教室资源，不发送通知，不写回教务系统。真实执行前必须人工复核最新忙闲、资质、工作量规则和教室开放状态。跨校区通勤、薪酬、审批和节假日不在 1.0.0 范围。
