# Workflow: Experiment Management

处理 EvoFlow 实验的全生命周期：提交、监控、查询、暂停/恢复/取消。

## 前置检查

### 1. CLI 安装与版本检查
```bash
# 检查是否已安装
pip show evoflow-sdk 2>/dev/null | grep Version

# 未安装则执行
pip install evoflow-sdk==1.1.1

# 验证 CLI 可用（实际入口）
python3.10 -m evoflow_sdk.cli.main --version
```
- 要求版本 **1.1.1**
- CLI 正确入口：`python3.10 -m evoflow_sdk.cli.main`（注意：不是 `python3`，需用 `python3.10`）
- 可在 shell 中设置别名方便使用：`alias evoflow-ctl="python3.10 -m evoflow_sdk.cli.main"`

### 2. API 配置
```bash
# 检查是否已登录（~/.evoflow-ctl/settings.json 存在则已配置）
python3.10 -m evoflow_sdk.cli.main account info
```
- 成功返回账户信息 → 跳过配置
- 报错 `API Key not configured` → 执行登录：
```bash
python3.10 -m evoflow_sdk.cli.main login \
  --api-url https://pro-service.evoflow.com \
  --api-key <用户提供的 API Key>
```
- API Key 格式：`bce-v3/ALTAK-...`
- 登录成功后再次执行 `account info` 确认余额

## 提交实验

### 第一步：选择提交模式
询问用户选择：
- **普通模式**（Normal）：直接提交到云端
- **混合模式**（Hybrid）：本地测试 → 提交 → 启动本地评估器

### 第二步：定位 config.yaml
```bash
find . -name "config.yaml" -type f 2>/dev/null | sort
```
- 1 个 → 直接使用
- 多个 → 询问用户选择
- 0 个 → 提供模板并请用户确认

### 第三步：确认实验目录
```bash
realpath $(dirname <path-to-config.yaml>)
```

### 第四步：设置实验名称
向用户确认实验名称（仅字母/数字/下划线，≤20字符）

### 第五步：预估费用（Dry-run）
```bash
python3 "$EVOFLOW_CTL" experiment create \
  --config ./config.yaml \
  --experiment-name <name> \
  --dry-run \
  --json
```
- 余额充足 → 告知预估费用，询问是否正式提交
- 余额不足 → 停止，告知费用与可用余额

### 第六步A：普通模式提交
```bash
python3 "$EVOFLOW_CTL" experiment create \
  --config <absolute-path>/config.yaml \
  --experiment-name <name> \
  -y --json
```
提交成功后每 30 秒轮询状态，直到完成 1~2 轮进化后停止

### 第六步B：混合模式
1. 本地测试：`python3 "$EVOFLOW_CTL" test --config ./config.yaml --timeout 300`
2. 提交实验（同上）
3. 启动本地评估器：
```bash
mkdir -p .evoflow && : > .evoflow/eval_trace
nohup python3 "$EVOFLOW_CTL" evaluator start \
  --experiment-id <id> \
  --evaluator-path ./evaluator.py \
  --max-concurrent=1 > .evoflow/eval_trace 2>&1 &
echo $! > .evoflow/evaluator.pid
```
4. 监控：轮询状态直到验证通过且完成 3~5 轮进化，然后转为每 1~5 分钟检查评估器健康

## 状态解析规则

解析 `experiment status <id> --json` 时区分：
- **outer status**：整体活跃状态
- **inner status**：
  - `INITIALING` → 验证阶段，progress = 验证进度
  - `RUNNING` → 进化阶段，progress = 进化进度
- 向用户展示：整体状态 / 当前阶段 / 阶段进度 / 进化轮次

## 其他实验操作

| 操作 | 命令 |
|------|------|
| 列表 | `python3 "$EVOFLOW_CTL" experiment list --status <s> --json` |
| 状态 | `python3 "$EVOFLOW_CTL" experiment status <id> --json` |
| 暂停 | `python3 "$EVOFLOW_CTL" experiment pause <id> --json` |
| 恢复 | `python3 "$EVOFLOW_CTL" experiment resume <id> --json` |
| 取消 | `python3 "$EVOFLOW_CTL" experiment cancel <id> --json` |
| 删除 | `python3 "$EVOFLOW_CTL" experiment delete <id> --json` |
| 日志 | `python3 "$EVOFLOW_CTL" experiment logs <id> --json` |
| 结果 | `python3 "$EVOFLOW_CTL" experiment results <id> --json` |
| 报告 | `python3 "$EVOFLOW_CTL" experiment report <id> --output <path> --json` |
| 账户 | `python3 "$EVOFLOW_CTL" account info` |

取消后展示 `credits_used` 和 `credits_refunded` 两项。
