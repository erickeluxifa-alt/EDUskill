---
name: skill-recommender
description: 当用户提出可能需要专业能力的问题，且本地已安装的skills都不适合时，从远端skill托管平台推荐并安装新skills。获取可用skills列表，分析用户意图，展示Top 3相关选项，并在安装前预览详细信息。
---

# Skill推荐器

该skill从远端平台推荐并安装新skills来帮助用户解决问题。

## 目的

当用户提出问题或请求任务时，该skill会：
1. 从远端平台获取可用的skills列表
2. 分析哪些skills最相关于用户的请求
3. 展示Top 3匹配的skills供用户选择
4. 安装前预览skill的详细信息
5. 用户确认后下载并安装到默认skills目录

## 何时使用

**自动触发时机：** 该skill应在以下情况自动调用：
- 用户提出的问题或任务可能受益于专业skill
- **本地已安装的skills都不适合处理该问题**
- 存在远端平台上的某个skill可能更好地处理该请求的可能性

**不应触发的情况：**
- 请求很简单且不需要专业知识
- **本地已有skill可以处理该问题**（优先使用本地skills）
- 用户明确询问与工具使用无关的一般信息

**重要：** 本地已安装的skills始终优先使用。只有当本地所有skills都不适合时，才触发此skill去远端查找。

## 使用方法

### 步骤1：从远端获取可用Skills

执行获取脚本从远端平台获取所有可用skills：

```bash
python3 scripts/fetch_skills.py
```

脚本会输出包含skill名称和描述的JSON。如果API调用失败，脚本会退出并输出"Failed to fetch skills from the platform."错误信息。

### 步骤2：分析和推荐

根据获取到的skill描述分析用户请求的相关性。考虑：
- 用户问题中的关键词和领域术语
- 请求的任务类型
- 用户意图与skill描述之间的语义相似度

选择Top 3最相关的skills。如果相关skills少于3个，只展示匹配度高的。

### 步骤3：向用户展示选项

以清晰的格式向用户展示推荐的skills：

```
发现以下技能可能对你有帮助:

1. **skill-name-1** - skill功能描述
2. **skill-name-2** - skill功能描述
3. **skill-name-3** - skill功能描述

需要我帮你安装哪个技能?（我会先展示详细信息供你确认）
```

### 步骤4：获取下载链接

用户选择skill后，获取其下载URL：

```bash
python3 scripts/get_download_url.py <skill_name>
```

脚本会输出下载URL。如果API调用失败，会退出并报错。

### 步骤5：预览Skill详细信息（安装前）

**关键步骤：在正式安装前，先展示skill的详细信息给用户确认。**

执行预览脚本：

```bash
python3 scripts/preview_skill.py <skill_name> <download_url>
```

脚本会：
- 自动检测当前环境（Standard 或 OpenClaw）
- 下载skill的zip文件到临时目录
- 解压并读取SKILL.md文件
- 提取skill的详细信息（名称、描述、功能概览、环境、安装路径）
- 输出JSON格式的详细信息
- 自动清理临时文件

向用户展示详细信息：

```
🔍 检测到当前环境: <Standard/OpenClaw>
📂 即将安装到: <安装路径>

📦 Skill详细信息:

名称: <skill_name>
描述: <description>

功能概览:
<overview前500字符>

确认安装这个技能吗? (输入"是"继续安装)
```

**等待用户明确确认后，再进行下一步安装。**

### 步骤6：安装Skill

用户确认后，执行安装：

```bash
python3 scripts/install_skill.py <skill_name> <download_url>
```

脚本会：
- 自动检测当前环境（Standard 或 OpenClaw）
- 显示安装目标路径
- 从提供的URL下载skill的zip文件
- 解压到 `~/.claude/skills/<skill_name>/` 或 `~/.openclaw/skills/<skill_name>/`
- 如果skill已存在则覆盖
- 输出安装成功确认

### 步骤7：确认安装完成

安装完成后，告知用户skill已就绪：

```
✅ 技能 '<skill_name>' 已成功安装!

环境: <Standard/OpenClaw>
安装位置: <完整路径>

现在可以使用该技能来处理你的请求了。
```

## 错误处理

**如果API调用失败**（获取skills或获取下载URL），向用户回复：

```
抱歉,暂时没有找到合适的技能来解决这个问题。你可以直接告诉我需要做什么,我会尽力帮助你。
```

**如果远端没有合适的skill**，告知用户：

```
远端平台没有找到特别匹配的技能。我会用现有能力尽力帮你处理这个问题。
```

不要自动重试失败的API调用。使用现有能力继续对话。

## 重要提示

- **触发逻辑：** 只有当本地已安装的skills都不适合时，才触发此skill
- **安装前必须预览**：使用preview_skill.py展示详细信息，获得用户明确确认
- **智能环境检测**：自动基于 skill-recommender 的实际位置确定安装目录，无需硬编码路径
  - 新skill将安装到与skill-recommender相同的父目录（skills目录）
  - 自动适配所有遵循标准目录结构的agent（Standard、OpenClaw、或其他自定义agent）
  - 支持自定义skills目录位置
- API端点和访问令牌在脚本文件中配置，可能需要更新
- Skills安装目录示例：
  - Standard: `~/.claude/skills/`
  - OpenClaw: `~/.openclaw/skills/`
  - 自定义: `~/.your-agent/skills/` 或任意自定义路径
- 安装时会覆盖同名的现有skills
- 最多展示3个相关skills，避免让用户感到困扰
