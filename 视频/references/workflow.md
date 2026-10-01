# HyperFrames 视频制作完整工作流

## 总览

```
文章/文案 → [Step 1] 脚本分段 → [Step 2] TTS 配音 + 精确计时 → [Step 2.5] 时间线对齐 → [Step 3] HTML 编排 → [Step 4] Lint + 渲染 → MP4
```

---

## Step 1: 文章 → 脚本分段

### 输入
- 原始文章 / 文案（任意格式）

### 输出
- `script.txt`：口语化、分段好的视频旁白文案

### 操作要点
1. 将原文精简为适合口播的语言（短句、口语化）
2. 按叙事节奏分段，每段独立成行
3. 总时长控制在 90–180 秒（短视频最优区间）
4. 每段约 10–18 秒，共 8–15 段

### 示例
```
你有没有这样的感觉？知道AI很重要，看了很多内容，但就是不知道自己能用它来干啥。

一个月前，小婷也是这样。她是一个宝妈，不懂代码，不会编程，辞职在家带娃...
```

---

## Step 2: 脚本 → TTS 配音 + 精确时间轴

### 2a. TTS 合成（自动化）

使用 Skill 内置的 `scripts/tts.py` 一键生成。**强烈推荐 `--timed` 模式**，逐段测量实际音频时长，避免后续时间线错位。

```bash
# 默认：edge-tts + 精确计时
python3 tts.py --timed --output-timestamps timeline.json script.txt narration.wav

# 腾讯云 TTS + 精确计时
export TTS_PROVIDER=tencent
export TENCENT_SECRET_ID=AKIDxxxxx
export TENCENT_SECRET_KEY=xxxxxxxx
python3 tts.py --timed --output-timestamps timeline.json script.txt narration.wav
```

输出文件：
- `narration.wav`：完整配音音频
- `timeline.json`：精确时间戳（每段 start/end 精确到 0.1s）
- 终端输出：可直接复制的 JS SUBTITLES 代码段

### 2b. 为什么必须用 `--timed`？

**估算时长不可靠。** `tts.py` 中 `len(line)/3.8` 的估算公式与实际 API 音频差距可达 30–40%。典型案例：

| 引擎 | 估算时长 | 实际音频 | 偏差 |
|------|---------|---------|------|
| edge-tts | 104.7s | ~126s | +20% |
| 腾讯云 TTS | 104.7s | 95.5s | -9% |

如果用估算值直接写入 HTML 字幕数组，视频后半段会出现「音频还在播，字幕已结束」的严重错位。

`--timed` 通过逐段生成→测量 PCM 字节数→计算实际秒数，精度 0.1s。

### 2c. 时间轴格式

`timeline.json` 输出格式：
```json
[
  { "start": 0.5, "end": 5.2, "text": "开场文案..." },
  { "start": 5.6, "end": 12.1, "text": "第二段..." }
]
```

终端同时输出可直接复制的 JS 代码段，粘贴到 `index.html` 的 `SUBTITLES` 数组即可。

---

## Step 2.5: 时间线精确对齐（⚠️ 强制步骤）

**这一步不能跳过。** 估算时间戳与真实音频之间存在不可忽视的误差。

### 操作步骤

1. **确认音频时长**
   ```bash
   ffprobe -v quiet -show_entries format=duration -of csv=p=0 narration.wav
   # 示例输出: 95.50
   ```

2. **更新 hyperframes.json duration**
   将音频总时长 + 2~3 秒余量写入：
   ```json
   { "duration": 98 }
   ```

3. **将精确时间戳写入 index.html SUBTITLES 数组**
   复制 `tts.py --timed` 终端输出的 JS 代码段。

4. **对齐场景切换时间点**
   每个场景的 `master.set` 起止时间必须对齐对应字幕段的 start/end：
   ```javascript
   // 场景 3 对应字幕段 3（start: 28, end: 52）
   master.set("#s3", { display: "flex" }, 28);
   master.set("#s3", { display: "none" }, 52);
   ```

5. **验证对齐**
   ```bash
   bash render.sh check   # lint + render
   ```

---

## Step 3: HTML 编排（核心）

### 3a. 项目结构

```
project/
├── index.html          ← 核心：视频画面编排
├── hyperframes.json    ← 全局配置
├── narration.wav       ← 旁白音频
├── timeline.json       ← 精确时间戳（tts.py 输出）
├── script.txt          ← 脚本原文
├── tts.py              ← TTS 脚本
├── package.json        ← npm scripts
└── render.sh           ← 一键渲染脚本
```

### 3b. 场景拆解

将整个视频按叙事节奏拆分为 4–8 个场景，每个场景一个 `<section class="scene">`。

**场景切换代码模式**：
```javascript
master.set("#s1", { display: "flex" }, 0);       // 开场
master.set("#s1", { display: "none" }, 28);       // 场景 1 结束

master.set("#s2", { display: "flex" }, 28);
master.set("#s2", { display: "none" }, 52);
```
⚠️ 时间值必须来自 Step 2.5 的精确字幕边界，禁止使用估算值。

### 3c. 动画设计原则

- **入场动画**：`fromTo` 从 `opacity: 0` 到 `opacity: 1`，配合 y 位移或 scale
- **弹性效果**：数据展示、标题 Emphasis 使用 `back.out` 缓动
- **对话气泡**：左右交替出现，模拟聊天界面
- **字幕始终底部**：position absolute + z-index 100

### 3d. 配色策略

- 每场景独立渐变背景，用颜色区分情绪段落
- 字幕条：半透明深色底 + backdrop-filter blur
- 关键数字/标题：使用暖色渐变（橙→金）高亮

---

## Step 4: Lint + 渲染

### 4a. 渲染前必查

在渲染前确认：
- `ffprobe` 音频时长与 `hyperframes.json` duration 一致（±3s）
- `SUBTITLES` 来自 `--output-timestamps` 输出
- 场景切换时间点与字幕段边界对齐

### 4b. 一键渲染

```bash
# 完整流水线（TTS + lint + render）
bash render.sh

# 强制重新生成配音
bash render.sh tts --force

# 仅 lint + render
bash render.sh check
```

### 4c. 分步渲染

```bash
npx --yes hyperframes@0.6.56 lint
npx --yes hyperframes@0.6.56 render
```

**常见错误**：见 `references/lint-errors.md`

### 4d. 输出

渲染完成后，MP4 文件位于 `renders/` 目录下。

---

## Step 5: 发布（可选）

### 抖音/视频号发布文案

1. 标题（15–25 字）：设置悬念或提问，从结论场景截取
2. 正文（2–3 句）：核心观点 + 互动引导
3. 标签：3–5 个领域话题标签（如 #低代码 #程序员 #AI视频）
4. 封面：从视频结论场景截取大字标题画面
5. 发布时间：工作日 12:00-13:00 或 19:00-21:00

---

## 迭代修改

修改视频内容的标准流程：

1. 修改 `script.txt`（如有文案变更）
2. `bash render.sh tts --force` 重新生成配音
3. 将新的 `timeline.json` 时间戳写入 `index.html` SUBTITLES
4. 更新 `hyperframes.json` 中的 `duration`
5. `bash render.sh check`（lint + render）

**核心优势**：因为视频本质是代码，修改 → 重渲染完全可控，不需要像 PR/AE 那样「改一处，调全局」。
