# 目标考核对齐诊断 · README

> 一个面向一线教师与教研员的备课阶段"教学目标 ↔ 测验题"一致性预检工具。基于布鲁姆认知分类法和逆向设计理论，输出覆盖矩阵、失配对诊断、干预建议和综合评分。

## 一、核心场景

| 维度 | 说明 |
|---|---|
| **目标角色** | 中小学/高校教师；教研员；备课组长 |
| **触发时机** | 写完单元学习目标和测验/作业题后，发布给学生之前 |
| **教育行业属性** | 通用 K12 + 高等教育教学设计辅助 |
| **可复用范围** | 学科不限（中文描述性目标均可）；课时级或单元级 |
| **核心增益** | (1) 专家经验 SOP：布鲁姆分类 + 逆向设计的标准化预检流程<br>(2) 数据资产：内置约50个常用动词到6层级的映射字典 JSON 可独立复用<br>(3) 工具能力：覆盖率统计 / 失配检测 / 综合评分 |

## 二、目录结构

```
目标考核对齐诊断/
├── SKILL.md                # Skill 元数据+使用规范（触发入口）
├── README.md               # 本文件
├── scripts/
│   └── check_alignment.py  # 核心引擎（约230行，纯标准库）
├── data/
│   └── bloom_verbs.json    # Bloom 动词字典数据资产
└── samples/
    └── sample_input.json   # 示例输入
```

## 三、安装

将本目录复制到 AI 助手的 skills 目录下，命名为 `edu-objective-assessment-checker`：

```bash
cp -r "目标考核对齐诊断" "/home/gem/workspace/.claude/skills/edu-objective-assessment-checker"
```

完成后即可通过自然语言触发本 Skill。

## 四、快速开始

```bash
cd edu-objective-assessment-checker
python3 scripts/check_alignment.py \
        --json samples/sample_input.json \
        --bloom data/bloom_verbs.json \
        --out-dir ./output
```

预期产出：
- output/alignment_report.md：4 个目标的样例中应识别出 O1=记忆, O2=应用, O3=分析, O4=评价 并发现高阶低阶失配2处。

## 五、依赖与配置

仅 Python 标准库 (`argparse`, `csv`, `json`, `re`, `sys`, `dataclasses`, `pathlib`)。
无第三方 pip 包要求。

## 六、JSON Schema 示例

见 SKILL.md 第三节或 samples/sample_input.json 文件内容。

## 七、限制说明

1. v0.1 仅支持结构化 JSON 输入格式；下版本会提供自然语言粘贴模式
2. bigram 匹配是粗粒度语义近似方法；建议结合 explicit_objective_ids 提升精度
3. 内置 Bloom 动词字典 ~50 条常见词；未识别时返回 unknown 但仍参与匹配判断

## 八、交付物料清单

| 物料 | 路径 |
|---|---|
| Skill 主文件 | scripts/check_alignment.py (~230 行) |
| 动词字典 | data/bloom_verbs.json |
| 示例输入 | samples/sample_input.json |
| 技能元信息 | SKILL.md |
| 本文档 | README.md |
