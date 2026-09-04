# 课堂活动设计包生成器

## 核心场景
面向教师、教研员、班主任，把一节课的目标和现实限制转成能在教室里执行的活动脚本。适用于高校、中职、中小学和企业培训等需要课堂互动的场景。

## 触发方式
可使用“设计一节课堂活动”“生成分组讨论方案”“把这些教学目标转成课堂互动脚本”等表达触发。

## 输入与输出
输入 JSON：课程、主题、分钟数、人数、目标，可选课堂限制和活动模式。输出 JSON 中包含结构化活动包及 Markdown 方案；错误输入返回错误清单。

```bash
python3 scripts/design_activity.py examples/sample_input.json --output /tmp/activity.json
```

## 依赖与限制
仅依赖 Python 3 标准库，离线运行。生成结果使用通用教学规则，不替代教师对学科内容、特殊教育需要和校规的判断；不会连接或写入 LMS、教务系统、群聊，也不会自动发送。

## 交互与副作用
生成结果最后包含预览确认清单。复制到 LMS、打印、发布群聊或调整正式课表前，必须由教师确认；本 Skill 只负责生成和校验，不执行这些动作。

## 交付物料
`SKILL.md`、`references/activity-rules.md`、`scripts/design_activity.py`、`examples/sample_input.json`、`tests/test_design_activity.py`、`tests/query-matrix.md`。
