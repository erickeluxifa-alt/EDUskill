# 听课反馈与复课验证助手

把督导、教研员的听课记录转成可审核的证据化反馈。核心增益是沉淀课堂观察 SOP，保留证据链，并把“问题”落到下一次可观察的教学行为。

## 适用范围
基础教育、职业教育、高等教育的常态课、公开课、磨课和复课。

## 运行

```bash
python3 scripts/observe_feedback.py examples/sample_observation.json --out-dir /tmp/lesson-observation-feedback
```

输入示例见 `examples/sample_observation.json`。输出 Markdown 供人工沟通，JSON 供后续教学质量闭环或复课记录复用。

## 交互与边界

只生成“待人工确认”的反馈草稿，不发送消息、不写入 LMS/SIS、不做绩效或教师等级判定。结果会写入用户指定的本地输出目录，不上传；输入中的课堂或学生敏感信息不会自动脱敏，请先使用脱敏数据。非法观察记录会进入 warnings；全部记录非法时退出并返回输入错误。
