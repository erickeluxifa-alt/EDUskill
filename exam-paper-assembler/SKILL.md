---
name: exam-paper-assembler
displayName: 试卷组卷助手
description: 面向命题教师、教研组与教务部门的自动组卷工具。何时使用：已有考试双向细目表（或可直接描述知识点权重、题型分值、难度目标）和课程题库时，需要自动完成选题、按知识点覆盖与难度匹配约束组卷、生成可打印试卷（学生版/教师版含答案）与组卷报告（缺口清单、难度分布、覆盖统计）时使用。题型覆盖单选、多选、判断、填空、简答、综合应用等，输出 Markdown/JSON，并配套试卷预览组件（HTML，支持桌面/移动端与打印）。
version: 1.0.0
author: ht
trigger:
  - 帮我组一套卷子
  - 自动生成试卷 / 组卷
  - 根据细目表选题组卷
  - 生成周测/月考/期中期末试卷
  - 从题库抽题
---

# 试卷组卷助手

## 目标
面向命题教师、教研组、教务的自动组卷工具：输入「考试双向细目表」（兼容 exam-blueprint-generator 的输出格式，也可手工编写）与「课程题库」，工具按知识点权重分配题量、按难度目标匹配选题、自动去重与补缺，输出可打印试卷（学生版 / 教师版含答案）和组卷报告，并配套纯前端试卷预览组件支持打印与存档。

## 输入

### 细目表 JSON（--blueprint）
```json
{
  "course": "Python程序设计",
  "exam": "2026年秋季学期期中考试（模拟）",
  "total_marks": 100,
  "knowledge_points": [
    {"name": "基础语法", "weight": 0.2, "level": "了解"}
  ],
  "question_types": [
    {"name": "单项选择题", "count": 12, "marks": 2, "difficulty": "易"}
  ],
  "difficulty_target": {"易": 0.3, "中": 0.5, "难": 0.2}
}
```
字段说明与 exam-blueprint-generator 一致；`question_types[].difficulty` 取「易/中/难/混合」，混合=不约束难度。

### 题库 JSON（JSON）
```json
{
  "questions": [
    {
      "id": "Q0001", "type": "单项选择题", "kp": "基础语法",
      "difficulty": "易", "marks": 2,
      "stem": "下列哪个是合法 Python 变量名？",
      "options": ["1var", "_x", "class", "None"],   // 可选，选项文本可带 A. 前缀（自动去除）
      "answer": "B", "explanation": "解析文本（可选）"
    }
  ]
}
```
- `type` 必须与细目表题型同名；`kp` 与知识点同名；`difficulty` 只取「易/中/难」。

## 执行
```bash
python3 scripts/assembler.py --demo                                   # 内置示例跑通全流程
python3 scripts/assembler.py -b examples/sample_blueprint.json -k examples/sample_bank.json
python3 scripts/assembler.py -b x.json -k y.json --format json --out paper --seed 42
python3 scripts/assembler.py -b x.json -k y.json --no-answers         # 学生版（不含答案）
python3 scripts/assembler.py -b x.json -k y.json --gap-mode warn      # 允许缺题的容错模式
```

## 输出
- Markdown 试卷（默认）：学生作答区 + 教师版答案与解析 + 组卷报告（组题数、总分对齐、难度分布、知识点覆盖、缺口/预警）。
- `--format json`：结构化试卷与报告，可直接交给前端组件 `components/paper-preview.html` 渲染预览与打印。
- `--out` 指定输出前缀，自动加 `.md` / `.json` 后缀；`--seed` 控制随机种子保证可复现。

## 组件：试卷预览（components/paper-preview.html）
纯本地 HTML（无网络依赖）：加载组卷 JSON → 渲染为试卷样式（题型分组、选项、答案解析开关、打印存 PDF、复制样例 JSON）。
- 桌面与移动端（≤640px）自适应；`@media print` 打印排版。
- 渲染过程全部使用 `textContent`，天然免疫 XSS；数据可粘贴或通过文件选择器注入。

## 规则与边界
- 组卷策略：知识点题量按权重分配（最大余数法）；难度优先匹配，无精确匹配时退而选最接近难度并告警。
- 缺题处理：默认（strict）有缺口即拒绝并列出缺口清单；`--gap-mode warn` 输出缺口提示继续生成。
- 自动去重：同一题库同一卷不重复选题；跨知识点回退补题会明确告警。
- 总分校验：实际选题总分与 `total_marks` 不一致即阻断（strict）或显著告警（warn）。
- 用户可控文本（课程名/题干/选项等）全部输出前 HTML 转义，长度裁剪 200 字符，防注入。

## 安全
脚本零依赖、纯本地：无 shell 调用、无 eval、无网络请求；示例数据均为模拟数据（`sample_bank.json` 中题面为占位文本，不用于真实教学）。