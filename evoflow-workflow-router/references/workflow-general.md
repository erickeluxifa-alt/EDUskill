# Workflow: General Optimization

通用进化算法优化工作流，适用于路径规划、调度排班、背包问题、ML 超参数调优及其他未明确归类的优化任务。
集成了 8 大行业场景专属建模策略，根据用户描述自动匹配最近似的场景模板。

## 场景识别规则

读取用户问题描述后，优先匹配以下 8 大场景。命中后直接加载对应的建模策略，无需用户手动选择：

| 关键词 | 场景 | 建模策略 |
|--------|------|----------|
| 生产排程、排产、换型、工序、设备利用率 | 生产排程优化 | 见 §1 |
| 物流调度、配送路径、VRP、末端配送、运输里程 | 物流调度优化 | 见 §2 |
| 需求预测、销量预测、补货计划、SKU预测 | 需求预测 | 见 §3 |
| 工艺参数、良率、注塑、配方、热处理 | 工艺参数优化 | 见 §4 |
| 库存补货、安全库存、缺货、积压清理 | 库存与补货优化 | 见 §5 |
| 成本优化、降本、运营成本、采购成本 | 成本优化 | 见 §6 |
| 资源分配、人员排班、预算分配、项目人员 | 资源分配优化 | 见 §7 |
| 其余情形（TSP、图着色、超参数等） | 通用复杂问题 | 见 §8 |

---

## §1 生产排程优化

**必须收集：**
- 订单信息（数量、交期、优先级）
- 设备/产线（产能、换型时间、维护计划）
- 工艺路线（工序顺序、标准工时）

**建模要素：**
- 决策变量：每台设备上各订单的加工顺序和开始时间
- 目标函数：最大化设备利用率 / 最小化最大完工时间 / 最小化换型次数（多目标加权）
- 硬约束：交期不可违反；工序前后依赖；设备不能并行处理同一工序
- 软约束：均衡各产线负荷；优先级高的订单优先排入

**evaluator.py 核心逻辑：**
```python
def evaluate(solution):
    # solution: [[设备0的订单序列], [设备1的订单序列], ...]
    makespan = calc_makespan(solution, orders, machines)
    tardiness = calc_tardiness(solution, orders)
    changeover = calc_changeover(solution, machines)
    # 多目标加权
    score = -(0.5 * makespan + 0.3 * tardiness + 0.2 * changeover)
    return score
```

**期望输出：** 甘特图 HTML（路由到 visualization 工作流）+ 关键指标对比表

---

## §2 物流调度优化（VRP）

**必须收集：**
- 订单（收货地址、重量/体积、时效要求）
- 车辆（车型、载重上限、出发仓库、班次时间）
- 距离/时间矩阵（用户提供或基于坐标估算）

**建模要素：**
- 决策变量：每辆车服务的订单集合及访问顺序
- 目标函数：最小化总里程 / 成本 / 车辆使用数
- 硬约束：容量不超载；时效窗口内到达；车辆工时上限
- 软约束：特定客户优先配送；区域限行时段

**evaluator.py 核心逻辑：**
```python
def evaluate(solution):
    # solution: {vehicle_id: [order_id, ...]}
    total_dist = 0
    for v_id, route in solution.items():
        if not check_capacity(v_id, route): return -1e9  # 硬约束惩罚
        if not check_time_window(v_id, route): return -1e9
        total_dist += calc_route_dist(route, dist_matrix)
    return -total_dist
```

**期望输出：** 每辆车路线列表 + 预计完成时间 + 整体成本汇总表（可视化路径图）

---

## §3 需求预测

**必须收集：**
- 历史销量数据（至少 8~12 周或 6 个月）
- 预测对象（SKU、区域、时间粒度）
- 预测用途（指导补货 / 生产排程 / 仓储容量）

**建模要素：**
- 特征工程：趋势项、周期项（周/月/年）、促销哑变量、节假日
- 模型策略：时序分解 + 进化算法校准残差修正量
- 评估指标：MAPE / WAPE / 偏差方向

**evaluator.py 核心逻辑：**
```python
def evaluate(solution):
    # solution: 预测修正向量（各期的加减量）
    adjusted_forecast = base_forecast + solution
    mape = np.mean(np.abs((actual - adjusted_forecast) / actual))
    bias = np.mean(adjusted_forecast - actual)  # 偏差惩罚
    return -(mape + 0.1 * abs(bias))
```

**期望输出：** 按周/月分解预测表 + 置信区间 + 重点风险提示

---

## §4 工艺参数优化

**必须收集：**
- 历史实验数据（参数组合 + 对应结果指标）
- 当前基准方案（参数值 + 良率/能耗基准数值）
- 参数约束范围（每个参数的上下界）

**建模要素：**
- 决策变量：连续参数向量（温度、压力、比例等）
- 目标函数：最大化良率 / 最小化能耗（多目标时用帕累托前沿）
- 约束：参数范围硬约束；稳定性要求（方差约束）
- 推荐算法：差分进化（DE）/ 高斯过程替代模型

**evaluator.py 核心逻辑：**
```python
def evaluate(solution):
    # solution: [param1, param2, ...]
    if not check_constraints(solution, bounds): return -1e9
    predicted_yield = surrogate_model.predict([solution])[0]
    predicted_energy = energy_model.predict([solution])[0]
    return 0.7 * predicted_yield - 0.3 * predicted_energy
```

**期望输出：** 推荐参数组合 + 与基准方案对比 + 关键影响参数排序

---

## §5 库存与补货优化

**必须收集：**
- 各 SKU 当前库存量、在途量
- 近期销量数据（3 个月以上）
- 供应商交货周期、最小起订量（MOQ）

**建模要素：**
- 决策变量：各 SKU 补货数量和时间点
- 目标函数：最小化（持有成本 + 缺货惩罚 + 采购成本）
- 硬约束：仓储容量上限；预算上限；MOQ
- 软约束：重点 SKU 优先保障；临期品先消化

**evaluator.py 核心逻辑：**
```python
def evaluate(solution):
    # solution: {sku_id: (replenish_qty, replenish_day)}
    holding_cost = calc_holding(solution, inventory, sales_forecast)
    stockout_penalty = calc_stockout(solution, inventory, sales_forecast)
    purchase_cost = calc_purchase(solution, prices)
    if exceeds_capacity(solution) or exceeds_budget(solution): return -1e9
    return -(holding_cost + stockout_penalty + purchase_cost)
```

**期望输出：** 各 SKU 补货建议表（含数量、时间、优先级）+ 高风险 SKU 清单

---

## §6 成本优化

**必须收集：**
- 成本明细（各成本项分类和金额，近 3~6 个月）
- 当前成本基线
- 目标降本比例 / 金额

**建模要素：**
- 决策变量：各成本项的调整方案选择（离散优化）
- 目标函数：最大化成本节省
- 硬约束：不影响交付时效/质量/服务水平
- 已排除方向：用户已尝试过的方法直接跳过

**evaluator.py 核心逻辑：**
```python
def evaluate(solution):
    # solution: [option_idx for each cost_item]  # 每项选择的优化方案
    total_saving = sum(savings[i][solution[i]] for i in range(n_items))
    quality_impact = sum(quality_costs[i][solution[i]] for i in range(n_items))
    if quality_impact > max_quality_impact: return -1e9
    return total_saving
```

**期望输出：** 成本构成分析 + 可执行优化方案列表（含预期节省金额和实施难度）

---

## §7 资源分配优化

**必须收集：**
- 可用资源（人员/设备技能标签、可用时间窗）
- 待分配任务（优先级、所需技能、工期、截止时间）
- 资源上限约束（每人/设备工时上限、预算总额）

**建模要素：**
- 决策变量：任务→资源的分配矩阵
- 目标函数：最大化资源利用率 × 任务完成率
- 硬约束：技能匹配；工时不超载；P0 任务必须按时完成
- 软约束：同一任务同一人负责；均衡工作量

**evaluator.py 核心逻辑：**
```python
def evaluate(solution):
    # solution: [resource_id for each task]
    for task_id, res_id in enumerate(solution):
        if not skill_match(task_id, res_id): return -1e9
        if overload(res_id, solution): return -1e9
    completion_rate = calc_p0_completion(solution, tasks, resources)
    utilization = calc_utilization(solution, resources)
    return 0.6 * completion_rate + 0.4 * utilization
```

**期望输出：** 资源分配方案表 + 关键取舍说明 + 潜在风险与应对建议

---

## §8 通用复杂问题（含 TSP / 图着色 / ML 超参数等）

适用于不属于 §1~§7 的任何组合优化问题。

**问题建模五要素：**
- 决策变量：优化对象是什么？（路径顺序、分配方案、参数取值）
- 目标函数：优化方向（最小化距离/成本、最大化效益/精度）
- 约束条件：硬约束（必须满足）vs 软约束（尽量满足）
- 输入规模：节点数、任务数、变量维度
- 基准参考：有无历史最优解或理论下界？

**方法选择矩阵：**

| 问题特征 | 推荐方法 |
|----------|----------|
| 排列/路径类（TSP/VRP） | 遗传算法（GA）+ OX 交叉/2-opt 变异 |
| 连续参数优化 | 差分进化（DE）/ PSO |
| 多目标 | NSGA-II / MOEA/D |
| 大规模组合 | 蚁群优化（ACO）/ 模拟退火（SA）|
| ML 超参数 | 贝叶斯优化 / 进化策略 |
| 结构性约束强 | 约束优化 GA + 罚函数 |

**标准三件套：**
```yaml
# config.yaml
evolve_config:
  max_iterations: 100
  population_size: 100
  num_islands: 4
initial_program: "init.py"
evaluator: "evaluator.py"
system_message: "prompt.md"
```

**默认假设声明：**
若问题描述不完整，默认：目标函数为最小化；无时间窗或容量约束；单目标优化。
并在输出中明确标注以上假设，请用户确认。

---

## 执行流程

```
Step 1 — 场景识别
  按上方关键词表匹配，加载对应场景（§1~§8）的建模策略

Step 2 — 信息核查
  核对必填项是否齐全；缺失时询问用户补充

Step 3 — 生成三件套
  config.yaml + init.py + evaluator.py
  输出到 /home/gem/workspace/.ark/output/evoflow-exp_<date>/

Step 4 — 本地验证
  验证 evaluator 可运行，sample_solution 能返回有效分数

Step 5 — 移交
  若用户需提交云端 → 路由到 workflow-experiment.md
  若用户需可视化 → 实验完成后路由到 workflow-visualization.md
```
