---
name: credit-progress-checker
displayName: 学分达标预检助手
description: 面向教学秘书、教务处、班主任和毕业班学生的学分毕业预检工具。何时使用：需要核对某学生或全班学生是否达到毕业学分要求、哪些必修课未通过或缺修、选修/任选学分类別缺口、按培养方案对照成绩单生成学分对账报告时使用。
version: 1.0.0
author: ht
trigger:
  - 帮我查XX能不能毕业 / 毕业学分够不够
  - 预检一下学生的学分达标情况
  - 按培养方案核对成绩单学分
  - 哪些必修课还没过 / 缺哪些课
  - 学分对账 / 毕业资格预检
---

# 学分达标预检助手（credit-progress-checker）

## 目标
把「培养方案」与「成绩单」自动比对，按类别核算必修课逐门对照（通过/缺修/未通过）、选修/任选学分池达标、总学分要求校核，输出可提交教务复核的 Markdown 报告，支持一键查看缺课清单与结构化 JSON 结果，让教学秘书 3 分钟内完成一个班级的毕业资格预检。

## 输入
1. 培养方案（JSON 或 CSV，表头支持中英文别名）：

```json
{
  "major": "计算机科学与技术",
  "plan": "2022 级培养方案",
  "min_credits": 170,
  "categories": {"必修": {"required_credits": 116}, "选修": {"required_credits": 24}, "任选": {"required_credits": 30}},
  "courses": [
    {"id": "CS101", "name": "高等数学(一)", "credits": 5, "category": "必修"}
  ],
  "aliases": [{"name": "高等数学(一)", "alias": ["高等数学", "高数"]}]
}
```

2. 成绩单（CSV 首行表头，或 JSON 数组 / `{"records":[...]}`）：
`学号,姓名,课程编号,课程名称,成绩,学分`（支持 成绩=数字/等级 A-F/优良好/及格-不及格/通过-Pass）

## 执行

```bash
python3 scripts/credit_checker.py plan.json transcript.csv
python3 scripts/credit_checker.py plan.json score.json --out report.md --json-out result.json --csv-out missing.csv
python3 scripts/credit_checker.py plan.json score.csv --student 2022001 --pass-threshold 60
python3 scripts/credit_checker.py plan.json score.csv --pool-any          # 选修/任选按任意通过课程计
python3 scripts/credit_checker.py --demo                                  # 内置双学生示例
```

参数：
- `--student <学号>`：只分析指定学生；
- `--pass-threshold <数值>`：及格分阈值（默认 60）；
- `--min-credits <数值>`：最低总学分（覆盖培养方案配置）；
- `--pool-any`：任选/选修以「任意通过课程均计入」口径核算（默认仅计培养方案内课程）；
- `--out` / `--json-out` / `--csv-out`：报告/JSON/缺课清单导出路径（默认报告打 stdout）。

## 匹配与核算规则
1. 课程匹配优先级：课程编号（id 精确）→ 课程名称（精确）→ 别名 → 名称互相包含（双方 ≥3 字符才启用）；
2. 同一课程多次修读取最高成绩（重修/补考通过即记为通过）；
3. 必修逐门对照：列出全部「未通过 / 无成绩」课程及学分；选修 / 任选按类别学分池（仅通过的课程计入）；
4. 总学分：`min_credits`（培养方案配置或 `--min-credits` 覆盖）不足则提示缺口；
5. 成绩单中有课程不在培养方案时，报告列出「未在培养方案内的课程」提示人工核对（不计学分，`--pool-any` 时按池内计入）。

## 输出
- Markdown 报告：学生明细 + 类别学分表（要求/已修/差额/状态）+ 缺课清单 + 差额说明 + 未匹配课程提示；
- CSV 清单：`学号,姓名,类别,课程,学分,状态,成绩,备注`（自动防 Excel 公式注入，`= + - @` 开头单元格加 `'` 前缀）；
- JSON：结构化结果，便于二次接入 / 展示。

## 安全与依赖
- 零第三方依赖（仅 Python3 标准库），离线运行，不访问网络；
- 输入文件仅本地读取；输出文件由用户指定路径；
- 报告/表格文本做 Markdown 转义，CSV 导出做公式注入防护；
- 不执行任何外部命令、不解析脚本内容。

## 验证
- 内置示例 `--demo`：张三未通过（数据结构 58 未过、选修缺 2 学分）、李四补考 74 通过后达标，覆盖通过与未通过路径；
- 目录样例数据 `examples/sample_plan.json + examples/sample_transcript.csv` 与 `tests/` 自测用例（见 README 自测记录）。