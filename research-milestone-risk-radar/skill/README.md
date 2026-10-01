# 科研节点风险雷达

## 一句话定位
把科研项目节点清单转成导师/项目负责人的优先跟进队列。

## 适用范围
- 目标角色：研究生导师、科研项目负责人、科研秘书
- 教育行业：高校研究生培养、课题组项目管理、产教协同课题
- 可复用场景：开题、中期检查、结题准备、周例会、月度项目盘点

## 核心增益
沉淀节点管理 SOP，利用截止日期、进度和依赖关系进行风险诊断，输出可复用的 JSON 接口和人工确认行动清单。

## 快速开始

```bash
python3 scripts/radar.py examples/sample_milestones.json --as-of 2026-08-30 --preview
python3 scripts/radar.py examples/sample_milestones.json --as-of 2026-08-30 --json > report.json
bash tests.sh
```

## 输入输出
输入为 JSON 数组或 `{ "milestones": [...] }`，必填 `id/project/milestone/owner/due_date/status`，可选 `progress/blocked_by/last_update/evidence`。文本输出适合会议快速浏览；JSON 输出包含 `validation`、`summary`、`risks`、`congestion`，可被周报或页面组件复用。

## 依赖与限制
仅依赖 Python 3 标准库。默认分析日取本机日期，建议正式使用时显式传入 `--as-of` 以便复盘。日期、状态和进度均来自用户导入数据；本工具不连接真实科研系统、不发送消息、不写回数据，不作为学生评价或处分依据。

## 交付物料
`SKILL.md`、`README.md`、`scripts/radar.py`、`examples/sample_milestones.json`、`tests.sh`。
