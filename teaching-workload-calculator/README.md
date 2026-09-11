# teaching-workload-calculator · 教师教学工作量核算与超限校验

离线核算每位教师的学期教学工作量，判定超上限 / 偏高 / 正常 / 低于下限，并把每一步折算系数摊开给人复核。纯 Python 3 标准库，无第三方依赖，不联网，不写回教务系统。

## 快速开始

```bash
python3 scripts/calc_workload.py --demo --json
python3 scripts/calc_workload.py --input examples/sample_input.json --out-dir output
cat data.json | python3 scripts/calc_workload.py --input - --strict
```

| 参数 | 说明 |
|---|---|
| `--input <file>` | JSON 输入文件，`-` 表示从 stdin 读取 |
| `--demo` | 使用 `examples/sample_input.json` 内置示例 |
| `--out-dir <dir>` | 报告输出目录，默认 `output` |
| `--json` | 只打印结构化结果，不落盘 |
| `--strict` | 打印结果；状态不为 `ok` 时返回退出码 2 |

`--input` 与 `--demo` 至少提供一个，否则报错退出。

## 输入格式

顶层必须是 JSON 对象，含 `term`（可选）、`rules`（可选）、`teachers`（必填）、`courses`（可选）、`supervisions`（可选）。

### teachers

```json
{ "id": "T01", "name": "教师甲", "title": "教授", "department": "计算机学院" }
```

`id` 必填且唯一，重复只保留首条并报 error。`name`/`title`/`department` 缺失时分别按 `未命名` / `未填` / `未分配院系` 处理。上限 500 人。

### courses

```json
{ "course_id": "C101", "name": "数据结构", "teacher_id": "T01",
  "type": "理论", "hours": 64, "students": 168, "merged_classes": 3, "is_new": false }
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `teacher_id` | 是 | 必须已在 `teachers` 中登记，否则该课不计入 |
| `hours` | 是 | 0~2000 的正数；`0`、负数、布尔、字符串均判为 error 且不计入 |
| `course_id` | 否 | 缺省按 `C<序号>`；同一教师重复课程号会告警并按两次授课累加 |
| `type` | 否 | 缺省 `理论`；不在 `course_type_coefficient` 中的类型按 1.0 计并告警 |
| `students` | 否 | 缺失或非正数时人数系数按 1.0 计，报告中标注原因 |
| `merged_classes` | 否 | 缺省 1；小于 1 按 1 计并告警 |
| `is_new` | 否 | 仅严格等于 `true` 时套用新开课系数 |

课程条目上限 3000，超出部分截断并报 error。

### supervisions

```json
{ "teacher_id": "T01", "kind": "thesis", "count": 8 }
```

`kind` 默认支持 `thesis`（毕业论文/设计指导）、`internship`（实习实践指导）、`competition`（学科竞赛指导）、`graduate`（研究生指导）；其他类型需在 `rules.supervision_hours` 中补充折算标准，否则该条判 error 不计入。`count` 必须是 0~500 的整数。

## 折算公式

```
课程折算 = hours × type_coef × size_coef × merged_coef × new_coef
merged_coef = 1 + merged_class_extra × (merged_classes − 1)
指导折算 = hours_each × count
合计 = Σ课程折算 + Σ指导折算
达标率 = 合计 / standard_workload
```

`size_coef` 按 `class_size_tiers` 从小到大匹配第一个 `students <= max_students` 的档位；全部不匹配时用 `oversize_coefficient`。

### 默认规则

| 规则项 | 默认值 |
|---|---|
| `standard_workload` | 320 |
| `min_workload` | 160 |
| `max_workload` | 480 |
| `high_ratio` | 1.2 |
| `course_type_coefficient` | 理论 1.0 / 实验 0.8 / 实践 0.6 / 体育 0.9 / 在线 0.7 |
| `class_size_tiers` | ≤60 → 1.0；≤90 → 1.1；≤150 → 1.2 |
| `oversize_coefficient` | 1.3 |
| `merged_class_extra` | 0.05（每多一个合班 +5%） |
| `new_course_coefficient` | 1.15 |
| `supervision_hours` | thesis 18 / internship 6 / competition 10 / graduate 30 |

`rules` 中的字典项按 key 合并（只覆盖你写的键），列表项整体替换，数值项直接替换。未知规则项忽略并告警；类型不匹配回退默认值。

阈值必须满足 `0 <= min_workload <= standard_workload <= max_workload`，否则三项整组回退默认并告警。

## 判定档位

按顺序判定，命中即止：

| 状态 | 条件 | 处置建议 |
|---|---|---|
| `over_limit` 超出上限 | `合计 > max_workload` | 按规定审批超课时或调减下学期任务 |
| `high` 偏高关注 | `合计 >= standard_workload × high_ratio` | 关注，暂不需处置 |
| `low` 低于下限 | `合计 < min_workload` | 核实是否漏报课程/指导，或补充教学任务 |
| `normal` 正常 | 其余 | — |

整体 `status`：存在 error 级问题、超限或不足教师时为 `needs_review`；`teachers` 非法或顶层不是对象时为 `data_error`；否则 `ok`。

## 输出

`--out-dir` 模式下生成两个文件：

- **`workload_report.json`** — `status` / `term` / `rules_applied`（实际生效的全部规则）/ `summary` / `teachers`（含逐门课系数与 `size_note`）/ `department_summary` / `issues`。
- **`workload_report.md`** — 教师工作量总表（按合计降序）、需重点处置名单、逐人折算明细、院系汇总、数据问题表、人工确认清单。

Markdown 中所有文本字段都会转义管道符与换行并截断，避免破表。

## 设计约束

- 未通过校验的课程/指导条目**不计入合计**，只进入 issues。这是有意设计：宁可显式报错，也不把错误数据算进考核。
- `hours`/`count` 等数值字段拒绝布尔值（`True` 不会被当作 1）、`NaN` 和无穷。
- 排序确定性：教师按 `(-合计, teacher_id)`，院系按 `(-总折算, 院系名)`，同输入必然同输出。
- 不写回 LMS/SIS，不发送通知，不触发审批或津贴发放。示例与演示数据均为模拟数据。

## 人工确认

折算系数与超课时上下限须以本校《教学工作量管理办法》为准，本工具只是按输入规则的复算。涉及绩效、津贴发放前必须由教务处与人事部门人工复核。
