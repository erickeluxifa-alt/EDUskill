---
name: exam-invigilator-planner
displayName: 考场编排与监考调度生成器
description: 输入考试场次、考场容量与监考信息，自动生成考场编排表与监考日程，明示考位/监考缺口。触发词：考场、监考、排考、期末考安排、考场编排。
---

# 考场编排与监考调度生成器

## 一句话定位

输入考试场次、考场容量与监考教师信息，自动生成无冲突的考场编排表和监考日程，并明示座位与监考缺口（零依赖、离线可跑）。

## 场景与目标角色

- **场景**: 教务处/院系教学秘书在期末、期中、补考安排前批量排考场（计算机类课程尤其需要精确座位数）；考务负责人按"回避任课班级、单日场次上限"约束派监考教师。
- **目标角色**: 教务处管理员、院系教学秘书、教学副院长助理、考务干事
- **触发时机**: 学期末排考阶段；接到考试清单后 3 分钟内输出可核对的编排草案
- **触发语句示例**: "帮我编排这学期期末考场和监考"、"给《高等数学A》安排考场"、"按班级人数拆考场并配监考教师"

## 输入

JSON（支持中英文字段别名，详见 README 输入规范一节）：

```jsonc
{
  "exams": [
    {"course": "高等数学A", "date": "2026-06-29", "slot": "上午",
     "classes": [{"name": "计算机2401", "count": 42}, {"name": "软件2402", "count": 40}]}
  ],
  "rooms": [{"id": "教1-101", "capacity": 90}, {"id": "教1-102", "capacity": 60}],
  "invigilators": [
    {"name": "张明", "teach_classes": ["计算机2401"], "max_per_day": 2,
     "unavailable": [{"date": "2026-06-30", "slot": "上午"}]}
  ],
  "rules": {"avoid_own_class": true, "min_invigilators_per_room": 1}
}
```

- 输入依赖：仅 JSON 文件（或 stdin 管道）；零第三方依赖，离线可运行。

## 处理逻辑

1. 顶层结构校验（exams/rooms/invigilators/rules，中英文别名兼容）
2. 逐场次解析：日期归一化（`2026-06-29` / `2026/6/29` / `2026年6月29日`）、班级人数校验
3. 贪心装座：按容量从大到小把班级切分进考场，座位不浪费且满足容量上限
4. 监考调度：每考场按"保底 1 人 + 每 50 人加 1（可配）"计算需要监考名额；候选按**同日已监考人数少 → 姓名**排序，逐个校验：
   - 不可用时段（unavailable，`*` 表示全天不可用）
   - 单日场次上限（max_per_day，缺省取规则默认 2 场）
   - 同时段冲突（同教师同日期同时段只能一考场）
   - 回避任课班级（avoid_own_class，默认开启）
5. 缺口显式告警：考位不足/监考不足分别列"error/fix"项，绝不静默编造
6. 输出 Markdown 报告或结构化 JSON；`--out` 仅显式指定时写文件

## 输出

- **Markdown**（默认）：`一、缺口与异常 → 二、考场编排表（考场|座位|班级分配|监考教师） → 三、监考日程（按教师） → 四、汇总`
- **JSON**（`--json` 或 `--out`）：`issues[] / plan[] / invigilator_schedule[] / summary`

## 用法

```bash
python3 scripts/exam_scheduler.py examples/sample_exam.json          # Markdown
python3 scripts/exam_scheduler.py examples/sample_exam.json --json   # 结构化结果
cat examples/sample_exam.json | python3 scripts/exam_scheduler.py --json   # stdin 管道
python3 scripts/exam_scheduler.py examples/sample_exam.json --out result.json
```

## 验证

- 内置自测：`bash scripts/run_selftest.sh`（30 条用例：主流程/同义字段/缺输入/边界/压测/XSS/冲突约束，通过率 100%）
- 已知限制：教室容量为硬约束不做跨教室合并超容；班级拆分按容量顺序，不保证"同班同室"；非整数容量或日期格式错误会跳过并告警；单日默认上限与回避规则仅供参考，最终发布需校对人名。

## 说明

- 本技能为示例/原型代码，数据为模拟数据，未接入真实教务系统。
- 开发者：ht · v1.0.0（2026-08-19）