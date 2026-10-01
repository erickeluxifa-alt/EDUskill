---
name: student-group-project-role-balancer
displayName: 学生项目小组角色均衡分配
version: 1.0.0
author: ht
description: 面向教师和教研员，根据学生能力、角色偏好、项目人数与角色覆盖要求生成可解释的小组角色分配方案，识别技能缺口与负担不均；纯离线预览，不修改学籍或成绩数据。
trigger:
  - 帮我分配项目小组角色
  - 生成学生小组分工方案
  - 检查小组角色是否均衡
  - 按学生特长安排项目任务
---
# 学生项目小组角色均衡分配

## 场景

小组项目启动前，教师需要把学生分成若干组，并为每组分配协调、研究、实现、记录、展示等角色。Skill 综合能力标签、角色偏好、组规模与角色覆盖要求，生成稳定、可解释、可人工调整的预览。

## 输入

```json
{
  "project": {"name": "校园节能方案", "group_count": 2, "group_size": 3},
  "roles": [
    {"id": "research", "name": "资料研究", "capacity": 1, "skills": ["research"]},
    {"id": "build", "name": "方案实现", "capacity": 1, "skills": ["technical"]},
    {"id": "present", "name": "展示汇报", "capacity": 1, "skills": ["communication"]}
  ],
  "students": [
    {"id": "S001", "name": "学生甲", "skills": ["research"], "preferred_roles": ["research"]}
  ],
  "rules": {"max_same_skill_in_group": 2, "avoid_same_role_preference": false}
}
```

必填：`project`、`roles`、`students`。学生 ID、角色 ID 必须唯一且非空；学生人数必须等于 `group_count × group_size`；每个角色的 `capacity` 为正整数，所有角色容量之和必须等于 `group_size`。能力和偏好使用输入中的字符串标签。

## 处理

1. 校验项目规模、角色容量、重复 ID、未知角色偏好和数据类型；错误输入不进入分配。
2. 按学生稳定 ID 排序，使用能力覆盖、角色偏好、组内技能重复和当前负担计算候选得分。
3. 逐组分配学生，再为每位学生分配尚未达到容量的角色；优先满足能力匹配，其次满足偏好，最后用学生 ID 做稳定打破平局。
4. 标记每组的角色覆盖、技能缺口、同技能集中和偏好未满足情况，不把分配结果视为教师最终决定。
5. 输出一份可预览方案和结构化审计数据，支持教师修改输入后重跑。

## 输出与交互

```bash
python3 scripts/balance_roles.py --demo --json
python3 scripts/balance_roles.py --input examples/sample_input.json --out-dir output
python3 scripts/balance_roles.py --input examples/sample_input.json --strict --json
```

输出 `role_plan.json` 和 `role_plan.md`。默认状态为 `REVIEW_REQUIRED`；存在错误、技能缺口或组规模问题时，`--strict` 返回退出码 2。工具只生成预览，不写回 LMS/SIS、不发送通知；教师确认后再在线下执行。输出目录可删除以撤销本次预览。

## 限制

纯 Python 3 标准库、零依赖、离线运行。示例数据为模拟数据。能力标签不能替代教师对学生协作关系、特殊支持和项目安全要求的判断；涉及未成年人隐私时应使用受控标识。
