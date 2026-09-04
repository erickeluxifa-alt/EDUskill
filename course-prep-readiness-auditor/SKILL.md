---
name: course-prep-readiness-auditor
displayName: 课前备课就绪度审计器
description: 检查课程或单节课备课材料是否具备目标、活动、评价、资源与差异化支持的可执行闭环，输出分级缺口和补齐清单。适用于教师、教研员和班主任；离线运行，不连接 LMS/SIS，不自动发布内容。
version: 1.0.0
author: ht
entrypoint: scripts/audit.py
---

# 课前备课就绪度审计器

## 场景
教师在上课前把教案、课程大纲或备课笔记整理成 Markdown、纯文本或 JSON，快速判断是否可以开课，以及最值得优先补齐的内容。

## 触发方式
- “检查这份教案能不能直接上课”
- “做课前备课完整性检查”
- “审计课程目标、活动和评价是否对齐”
- “给我一份备课缺口清单”

## 输入
JSON 对象支持以下字段：`course`、`lesson`、`audience`、`duration_minutes`、`objectives`、`activities`、`assessments`、`resources`、`differentiation`、`notes`。数组元素可以是字符串，也可以是包含 `name`/`description`/`objective_refs`/`minutes` 的对象。也支持用 `--text` 传入自然文本，脚本按关键词识别证据。

## 处理逻辑
1. 对五个就绪维度检查证据：目标、活动、评价、资源、差异化支持。
2. 检查目标是否被结构化活动和评价引用；检查活动时长是否超过课时；检查评价对象是否有产出或判定标准。
3. 按 `critical / high / medium / low` 生成缺口，给出最小补齐动作。自然文本和字符串条目只做维度存在性检查，不臆测目标对齐。
4. 以 100 分为基准按问题严重级别扣分（critical 18、high 12、medium 7、low 3），分数仅用于备课决策，不替代教师判断。

## 输出
默认输出 JSON；`--format md` 输出可读 Markdown。包含 `readiness_score`、`status`、`dimension_checks`、`alignment_checks`、`issues`、`next_actions` 和 `assumptions`。当存在高优先级缺口时，状态为 `needs_revision`；所有关键维度具备证据且无超时则为 `ready_for_review`。

## 交互与限制
脚本只生成审计预览，不写入 LMS/SIS、不发送通知、不替教师决定是否开课。缺少输入时输出可执行的补录清单；文本识别是保守启发式，正式教研需人工复核。

## 示例
```bash
python3 scripts/audit.py examples/sample.json --format md
cat lesson.json | python3 scripts/audit.py - --format json
python3 scripts/audit.py --text "目标：理解抽样。活动：小组练习。评价：出口条。资源：讲义。"
```
