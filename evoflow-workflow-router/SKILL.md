---
name: evoflow-workflow-router
displayName: EvoFlow 工作流路由器
description: >
  EvoFlow全链路工作流路由器。整合进化算法实验管理、结果可视化、数据分析三大能力，
  根据用户任务描述自动识别任务类型，路由到最匹配的工作流执行。
  触发词：EvoFlow、evoflow、进化算法、进化实验、优化问题、路径规划可视化、数据分析报告、提交实验
---

# EvoFlow Workflow Router

EvoFlow全链路智能路由器，将用户任务自动分发到以下三条专项工作流：

| 工作流 | 文件 | 适用场景 |
|--------|------|----------|
| experiment | references/workflow-experiment.md | 提交/管理 EvoFlow 实验任务、查看账户余额、查实验状态 |
| visualization | references/workflow-visualization.md | 将进化算法 Python 解决方案渲染为交互式 HTML 可视化页面 |
| analysis | references/workflow-analysis.md | 数据分析、指标监控、异常诊断、归因拆解、趋势预测 |
| general | references/workflow-general.md | 通用优化问题、路径规划、调度、ML 超参数调优等其他情形 |

## 路由规则

**优先级顺序：**

1. **用户显式指定**：用户直接说"用 experiment 工作流"或"visualization"，直接路由
2. **任务特征匹配**（按优先级）：
   - 包含关键词「提交实验、实验状态、账户余额、config.yaml、evaluator.py、evoflow-ctl、hybrid 模式」→ `experiment`
   - 包含关键词「可视化、HTML 页面、渲染结果、画出路径、TSP 结果、调度图、甘特图」→ `visualization`
   - 包含关键词「数据分析、数据质量、异常诊断、指标下跌、归因、A/B 实验、经营分析」→ `analysis`
   - 其余情形 → `general`

## 执行流程

```
Step 1 — Route
  读取用户任务描述，按路由规则确定唯一工作流

Step 2 — Delegate
  读取对应 references/workflow-*.md 文件
  完全遵照其中的步骤、工具调用和输出格式执行

Step 3 — Exit
  工作流执行完毕后，路由器职责结束
  如有不确定，默认路由到 general 并说明假设
```

> **重要**：路由器本身不嵌入任何步骤细节。所有执行逻辑均在对应的 workflow 文件中定义。
