---
name: lesson-observation-feedback
displayName: 听课反馈与复课验证助手
description: 将督导或教研员的课堂观察记录整理为证据化反馈、优先改进动作和下一次听课核验点；离线运行，不替代人工评价，不写入教务系统。
version: 1.0.0
author: ht
---

# 听课反馈与复课验证助手

## 场景
面向教学督导、教研员、院系负责人和骨干教师，在听课结束后 3-5 分钟内把零散记录转成可沟通、可跟踪的反馈预览。适用于基础教育、职业教育和高等教育的公开课、常态课、磨课与复课观察。

## 触发方式
- “把这份听课记录整理成反馈和改进建议”
- “分析课堂观察证据，给出下次复课检查点”
- “生成督导听课反馈，但先不要发送”

## 输入
JSON 对象必须包含 `course`、`grade`、`lesson_date`、非空 `observations`。每条观察建议包含：
`dimension`（`objective`/`interaction`/`evidence`/`differentiation`/`closure`）、`evidence`；可选 `impact`、`severity`（1-5）、`confidence`（1-5）、`id`。可选 `observer`。

## 处理
1. 校验顶层字段和观察记录；非法记录进入警告，不影响其他合法记录。
2. 按五个课堂维度归类，并保留原始证据与学习影响。
3. 用 `severity × confidence` 的平均分排序，最多输出 3 个优先维度。
4. 为每个优先维度生成一个小步改进行动和可观察的复课核验点。
5. 生成教师反馈草稿，但状态固定为“待人工确认”，不自动发送或提交。

## 输出
- `observation_feedback.md`：可直接审阅和修改的反馈预览。
- `observation_feedback.json`：可被质量闭环、复课记录或其他 Skill 复用的结构化结果。

## 本地运行
```bash
python3 scripts/observe_feedback.py examples/sample_observation.json --out-dir /tmp/lesson-observation-feedback
```

## 依赖与限制
仅依赖 Python 3 标准库；不连接 LMS/SIS/教务系统，不上传课堂数据，结果写入用户指定的本地目录，不对教师做等级判定。优先分是排序辅助，不是绩效分数；正式反馈须由观察人结合课程目标人工确认。
