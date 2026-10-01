---
name: teaching-workload-calculator
displayName: 教师教学工作量核算与超限校验
version: 1.0.0
author: ht
description: 面向教务秘书、院系负责人和教师本人，按课程类型、班级人数、合班数、新开课与各类指导任务折算每位教师的学期教学工作量，判定超上限/偏高/正常/低于下限，并输出可复核的折算明细与数据问题清单；纯离线运行，不写回教务系统、不触发绩效发放。
trigger:
  - 帮我核算教师教学工作量
  - 统计这学期每位老师的折算学时
  - 查一下哪些老师超课时了
  - 教学工作量有没有低于下限的老师
  - 按系数折算课程和指导工作量
---
# 教师教学工作量核算与超限校验

## 场景
学期末或学期初，教务秘书、院系教学负责人需要把每位教师的授课任务和指导任务折算成统一的"折算学时"，用于工作量考核、超课时审批和下学期任务分配。这类核算规则明确但计算繁琐，用 Excel 手工拉公式容易漏项、错档、算错合班系数。本 Skill 把折算规则显式化，一次性算完并把每一步系数摊开给人看。

适用于高校、职业院校的院系级核算（默认上限 500 位教师、3000 条课程记录）。不替代学校教学工作量管理办法，不做绩效或津贴的最终认定。

## 能力
1. 按 `课程类型 × 班级人数档 × 合班 × 新开课` 四类系数折算每门课的工作量。
2. 按毕业论文/实习/竞赛/研究生四类指导任务，按人数 × 每人折算学时累加。
3. 对每位教师给出合计、达标率，并判定四档状态：超出上限 / 偏高关注 / 正常 / 低于下限。
4. 输出院系汇总（教师数、总折算、人均、超限人数、不足人数）。
5. 校验数据质量：未登记教师、学时异常、人数缺失、未知课程类型、未知指导类型、非法阈值与档位，逐条给出 error/warning。
6. 规则可全量覆盖：阈值、类型系数、人数档、合班加成、新开课系数、指导折算标准都可在输入里改。

## 输入
```json
{
  "term": "2026-2027-1",
  "rules": {
    "standard_workload": 320,
    "min_workload": 160,
    "max_workload": 480,
    "high_ratio": 1.2,
    "course_type_coefficient": { "理论": 1.0, "实验": 0.8, "实践": 0.6 },
    "supervision_hours": { "thesis": 18, "internship": 6, "competition": 10, "graduate": 30 }
  },
  "teachers": [
    { "id": "T01", "name": "教师甲", "title": "教授", "department": "计算机学院" }
  ],
  "courses": [
    { "course_id": "C101", "name": "数据结构", "teacher_id": "T01",
      "type": "理论", "hours": 64, "students": 168, "merged_classes": 3, "is_new": false }
  ],
  "supervisions": [
    { "teacher_id": "T01", "kind": "thesis", "count": 8 }
  ]
}
```
`teachers` 必填且 id 唯一；`courses`/`supervisions`/`rules` 均可省略，省略时用内置默认规则。`hours` 必须是 0~2000 的正数，`students` 缺失或非正数时人数系数按 1.0 计并在报告中标注。`kind` 只认 `thesis`/`internship`/`competition`/`graduate`（或在 `supervision_hours` 里自行补充）。

## 处理
1. 合并规则：未知规则项忽略并告警，类型不匹配回退默认值。
2. 校验阈值必须满足 `0 <= min <= standard <= max`，否则整组回退默认；人数档按上限升序排序，非法档位剔除。
3. 逐门课折算：`converted = hours × type_coef × size_coef × merged_coef × new_coef`，其中 `merged_coef = 1 + merged_class_extra × (merged_classes − 1)`，人数超出最大档时用 `oversize_coefficient`。
4. 逐条指导折算：`converted = hours_each × count`。
5. 判定顺序：`> max_workload` → 超出上限；`>= standard × high_ratio` → 偏高关注；`< min_workload` → 低于下限；其余正常。
6. 只要存在 error 级问题、超限或不足教师，整体状态即为 `needs_review`。

未通过校验的课程或指导条目**不计入合计**，只出现在数据问题清单里——这是有意设计，避免把错误数据算进考核。

## 输出
```bash
python3 scripts/calc_workload.py --demo --json                              # 只看结构化结果
python3 scripts/calc_workload.py --input examples/sample_input.json --out-dir output
python3 scripts/calc_workload.py --input - --strict < data.json             # 有问题时退出码 2
```
- `workload_report.json`：教师明细、逐门课系数、院系汇总、issues，可供页面或教务适配层消费。
- `workload_report.md`：教师工作量总表、需重点处置名单、逐人折算明细、院系汇总、数据问题、人工确认清单。

`--strict` 在状态不为 `ok` 时返回退出码 2，便于接入校验流水线；`--json` 与 `--strict` 都只打印不落盘。

## 交互
- **预览**：默认只生成本地报告，不写回任何系统。可先用 `--json` 看结果再决定是否落盘。
- **确认**：Markdown 末尾固定输出"人工确认"清单，明示折算系数须以本校管理办法为准、error 条目未计入、绩效发放前必须教务处与人事人工复核。
- **重试**：数据问题清单逐条标注 `courses[i]` / `supervisions[i]` 下标和原因，补齐后重跑即可。
- **撤销**：不产生副作用，删除输出目录即可完全回退。
- **错误提示**：JSON 解析失败、文件不存在、缺少参数均在 stderr 给出中文说明并返回退出码 2，不产生半成品输出。

## 限制
纯 Python 3 标准库，无第三方依赖，不联网。示例与演示数据全部为模拟数据。不写回教务系统、不发送通知、不触发任何审批或津贴发放流程。跨院系统一口径、教研/科研工作量折算、课酬计算不在本 Skill 范围内。
