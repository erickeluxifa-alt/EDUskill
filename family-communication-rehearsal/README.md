# 家校沟通预演器

## 核心场景

班主任或任课教师在家长会、电话沟通、阶段性反馈前，将经过核实的学生表现记录整理成“优势—事实—询问—支持—行动确认”的沟通预览，减少临场遗漏和标签化表达。

## 教育行业属性与增益

- 角色：班主任、任课教师、年级组长。
- 范围：中小学、职业教育和高校导师制下的常规家校/家生沟通准备。
- 增益：把沟通 SOP、隐私最小化和敏感措辞检查嵌入同一个离线工具。
- 可复用：可接作业、考勤、课堂观察等已核实摘要；不直接接入真实系统。

## 快速运行

```bash
python3 scripts/rehearse.py examples/sample_input.json --out-dir output
python3 -m unittest discover -s tests -v
```

输入为不超过 1 MB 的 JSON，各数组最多 20 项；输出为 `communication_preview.json` 和 `communication_preview.md`。仅依赖 Python 3 标准库。常规结果状态为 `REVIEW_REQUIRED`；出现安全信号时为 `SAFETY_ESCALATION_REQUIRED`，停止常规预演并转人工安全处置流程。

考勤原始记录应先由考勤跟进工具形成已核实摘要，再作为观察输入；安全事件则直接进入学校既有学生支持与危机处置流程，本工具不重复计算考勤阈值或代替安全分流。

## 交付物料

- `SKILL.md`：触发与工作流说明
- `scripts/rehearse.py`：离线处理器
- `examples/sample_input.json`：匿名样例
- `tests/test_rehearse.py`：核心自动化测试
- `references/communication_rules.md`：沟通与安全规则

## 限制

工具不会验证源系统事实真伪，不发送消息，不替代学校制度、教师专业判断或危机处置流程。正式沟通前必须由教师确认事实日期、沟通对象、隐私范围、措辞和行动项。
