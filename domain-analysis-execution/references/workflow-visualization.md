# Workflow: Solution Visualization

将进化算法 Python 解决方案渲染为交互式 HTML 可视化页面，展示"解的形态"而非进化过程。

## 输入收集

**必须项：**
- 问题描述（优化类型、规模、约束）
- Python 解决方案代码（进化后的最终结果）

**可选项：**
- 评估分数 / 适应度值
- 初始解（用于对比）
- 原始问题数据（节点坐标、任务列表等）

缺少必须项时，先向用户索取再继续。

## 理解解的语义 → 确定可视化类型

直接阅读代码，提取：
- 问题类型
- 解的核心数据结构
- 用于渲染的关键值

| 问题类型 | viz_type | 视觉形式 |
|----------|----------|----------|
| TSP / VRP / 路径规划 | `path_map` | SVG 坐标系 + 节点连线路径 |
| 调度 / 排班 | `schedule_grid` | 彩色块热力表格 |
| 背包 / 装箱 | `packing_rect` | SVG 堆叠矩形容器 |
| 图着色 / 社区检测 | `graph_color` | 节点着色图 |
| 作业调度 / 项目计划 | `gantt` | 水平甘特图 |
| 对比 / 多指标 | `bar_compare` | 对比柱状图 |
| ML / 神经网络 / 超参数 | `ml_viz` | 网络结构 / 训练曲线 / 超参热力图 |
| 其他 / 复杂策略 | `custom` | 关键指标仪表盘 + 文本描述 |

## 生成 HTML 文件

输出路径：`/home/gem/workspace/.ark/output/evoflow-viz_<date>/evoflow_viz_result.html`

### 页面布局
```
┌─────────────────────────────────────────────┐
│ [问题类型标签]  问题摘要        关键指标卡片  │
├────────────────────────────┬────────────────┤
│                            │                │
│   主可视化区域（≥50%）      │  解的亮点      │
│   路径 / 排班 / 装箱 / 甘特  │  分数 / 改进量 │
│                            │                │
├────────────────────────────┴────────────────┤
│   （可选）对比区 / 补充说明                   │
└─────────────────────────────────────────────┘
```

### 设计规范
- **配色**：背景 `#030810`，卡片 `#080f1e`，边框 `#112240`
- **强调色**：主色 `#00c8ff`（蓝），辅色 `#00ff88`（绿）
- **字体**：正文 Noto Sans SC，数字/代码 IBM Plex Mono（Google Fonts CDN）
- **动画**：各区域 fadeUp 依次入场；路径逐段绘制，柱状图从底部生长，节点弹入
- **交互**：鼠标悬停显示固定位置 tooltip，跟随鼠标，展示详细数值

### 技术栈
```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.5/babel.min.js"></script>
<script src="https://cdn.tailwindcss.com"></script>
```

### 数据处理原则
- **只读取代码中的数据字面量**，不执行 Python 代码
- 将提取的值硬编码到 HTML 中的 `SOLUTION_DATA` 常量
- 节点/任务数 > 100 时进行采样或聚合，避免视觉混乱
- 无法识别问题类型时，fallback 到 `custom` 仪表盘

## 交付

生成完毕后：
1. 使用 `cli upload <文件路径>` 上传
2. 在回复中附上下载链接，格式：`- evoflow_viz_result.html: [下载链接](URL)`
