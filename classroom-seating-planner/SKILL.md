---
name: classroom-seating-planner
displayName: 课堂座位编排与约束核验
version: 1.0.0
author: ht
description: 面向教师、班主任、监考教师和教务人员，根据教室座位、学生名单和分离/前排/禁用座位约束生成可解释的课堂座位表，并输出冲突清单与人工确认预览；纯离线运行，不写回教务系统。
trigger:
  - 帮我排课堂座位
  - 生成考试座位表
  - 安排学生座位并避开指定同学
  - 检查座位安排有没有冲突
  - 给需要前排的学生安排座位
---
# 课堂座位编排与约束核验

## 场景
教师、班主任或监考人员在上课、考试、分组活动前，根据学生名单和教室布局快速生成座位表。适用于基础教育、职业教育、高校课堂及小型考试，不替代学校对特殊教育、隐私和考试纪律的人工判断。

## 输入
```json
{
  "class_name": "高一3班",
  "room": {"rows": 4, "cols": 5, "blocked_seats": ["R1C5"]},
  "students": [
    {"id": "S01", "name": "学生甲"},
    {"id": "S02", "name": "学生乙"}
  ],
  "constraints": {
    "separated_pairs": [["S01", "S02"]],
    "front_row_ids": ["S01"]
  }
}
```
`R1C1` 是第一排第一列；前排默认指第一排。学生 ID 必须唯一，座位数量至少覆盖学生数。可选 `fixed_seats` 为 `{"S01":"R1C1"}`。

## 执行
```bash
python3 scripts/plan_seats.py --demo
python3 scripts/plan_seats.py --input examples/sample_input.json --out-dir output
python3 scripts/plan_seats.py --input examples/sample_input.json --json
```

## 输出
- `seating_plan.json`：座位、学生、约束状态和冲突的结构化结果，可供页面或教务适配层消费。
- `seating_plan.md`：可打印的座位表、未满足约束、人工确认清单。

## 处理规则
1. 先校验输入、重复学生、重复约束、座位容量和固定座位合法性。
2. 优先安排固定座位与 `front_row_ids`，再按约束度高低安排其他学生。
3. `separated_pairs` 视为不能相邻（含上下左右和对角线）； blocked seat 不参与安排。
4. 采用确定性回溯搜索；搜索失败时输出当前最佳方案和未满足约束，不声称全部满足。
5. 输入中的姓名只用于本地报告，Markdown 中会转义管道符和换行。

## 交互与限制
本 Skill 只生成预览，不写回 LMS/SIS、不发送通知、不修改原始名单。最终执行前应由教师人工确认学生隐私、特殊座位依据、考试规则和临时调位流程。没有真实系统接口，示例和演示数据均为模拟数据；大班或复杂动态约束建议接入专用排座服务后再复核。
