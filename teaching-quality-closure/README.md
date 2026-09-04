# 教学质量整改闭环助手

将课程评价、听课督导、教学检查或学生反馈转成可执行整改台账。适用角色：院系负责人、教学秘书、教研组长、任课教师。

## 快速使用

```bash
printf '%s' '{"findings":[{"description":"课程目标与作业要求不一致","severity":"high"},{"description":"个别学生无法访问实验资源","severity":"medium"}]}' | python3 scripts/quality_closure.py
```

输出按优先级排序的 JSON 台账，包含分类、责任角色、建议动作、目标日期、关闭证据和人工确认队列。默认离线运行，使用模拟输入，不接入真实教务、LMS 或消息系统；目标日期基于运行当天生成，仅作建议。

## 可组合接口

- 输入接口：标准输入 JSON，`findings` 或 `issues` 数组。
- 输出接口：标准输出 JSON；错误时退出码 2，并返回 `INVALID_INPUT`。
- 上层编排可读取 `register` 后渲染表格、生成会议议程或交给人工确认流。
