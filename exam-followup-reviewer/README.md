# exam-followup-reviewer「考后教学复盘助手」v1.0.0

考后复盘界面的收口环节：输入 `exam-score-analyzer` 的 analysis.json，一条命令产出「班级画像 + 共性薄弱归因 + 命题四象限 + 回流建议 + 帮扶名单」完整复盘。

## 快速开始

```bash
# 无需准备数据，跑演示
python3 scripts/followup_reviewer.py --demo --out-dir out/demo

# 真实数据（多班级横评）
python3 scripts/followup_reviewer.py --analysis examples/classA_analysis.json --analysis examples/classB_analysis.json --out-dir out/ab
```

## 目录结构

```
exam-followup-reviewer/
├── SKILL.md                      # 技能说明（full）
├── README.md                     # 快速上手（本文件)
├── scripts/
│   ├── followup_reviewer.py      # 主程序（零第三方依赖）
│   └── html_render.py            # 单文件 HTML 报告渲染器
├── examples/
│   ├── gen_demo_data.py          # 演示数据分析（复现式）
│   ├── classA_analysis.json      # 示例：计科2401（良好）
│   └── classB_analysis.json      # 示例：计科2402班（待提升）
└── tests/
    └── run_self_test.sh          # 31 条自测断言（全绿）
```

## 自测

```bash
bash tests/run_self_test.sh
# 结果: PASS=31 FAIL=0
```

## 口径速查

- 画像分 = 0.5×得分率 + 0.3×及格率 + 0.2×(1−低分率)
- 四级知识点档位与共性薄弱（≥2 班 <60%）归因
- 题目四象限 + 回流建议（下调难度/控制难度/维持/可加码）

完整口径、输入输出约定、安全边界与联动方式见 [SKILL.md](SKILL.md)。