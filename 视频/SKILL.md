---
name: hyperframes-video
description: "HyperFrames 视频项目生成器 — 基于 HTML+CSS+GSAP 的声明式视频制作工作流。将文章/文案自动转化为完整配音、字幕与动画的视频项目，支持一键渲染出 MP4。适用场景：公众号文章转视频、AI 故事视频制作、新媒体内容视频化、批量短视频生产。触发词：HyperFrames、HF 视频、HTML 视频、文章转视频、口播视频、一键出片。"
agent_created: true
---

# HyperFrames 视频项目生成器

基于 HyperFrames 引擎，将一段文案转化为完整的配音 + 字幕 + 动画视频项目，并通过一条命令渲染出 MP4 成品。

## 核心理念

**用写网页的方式做视频。** 视频的每一帧由 CSS 渲染，每一个动画由 GSAP Timeline 控制，每一个字幕由 JSON 时间戳驱动。最终通过 `npx hyperframes render` 输出 MP4。

## 工作流（五步）

### Step 1: 文章 → 脚本分段

将原始文案精简、分段为适合口播的视频脚本（`script.txt`）。

- 每段 10–18 秒，总时长 90–180 秒
- 短句、口语化、每段独立成行
- 按叙事节奏分段：开场 → 痛点 → 反转 → 高潮 → CTA

详见 `references/workflow.md` Step 1。

### Step 2: 脚本 → TTS 配音 + 精确时间轴

**TTS 配音（自动化）**

本 Skill 提供 `scripts/tts.py`，支持两种配音引擎，**凭据全部从环境变量读取，绝不硬编码**：

```bash
# 默认模式：edge-tts（微软免费，无需 API Key，中文效果好）
python3 tts.py script.txt narration.wav

# 精确计时模式（推荐用于生产）：逐段测量实际音频时长
python3 tts.py --timed --output-timestamps timeline.json script.txt narration.wav

# 腾讯云 TTS + 精确计时（客户自配凭据）
export TTS_PROVIDER=tencent
export TENCENT_SECRET_ID=AKIDxxxxxxxx
export TENCENT_SECRET_KEY=xxxxxxxxxxxx
python3 tts.py --timed --output-timestamps timeline.json script.txt narration.wav
```

⚠️ **绝对禁止硬编码 API Key 到代码中。** 所有凭据必须通过环境变量传入。

**为什么必须用 `--timed`？**

估算时长（`len(line)/3.8`）与 API 实际音频时长差距可达 30–40%。如果用估算时长直接写入 HTML 的 SUBTITLES 数组，渲染出来的视频字幕将严重错位——后半段音频还在播，字幕已经结束了。`--timed` 模式逐段生成→测量实际 PCM 字节数→输出精确到 0.1 秒的时间戳，彻底解决这个问题。

每个项目自动生成 `.env.example` 模板文件，客户复制为 `.env` 后填入自己的凭据即可。

### Step 2.5: 时间线精确对齐（⚠️ 强制步骤）

**这一步不能跳过。** 即使使用了 `--timed`，也需要手动将时间戳写入 HTML。

1. 运行 TTS 后，`tts.py` 会在终端输出可直接复制的 JS 代码段：
   ```
   { index: 0, start: 0.5, end: 5.2, text: "开场文案..." },
   { index: 1, start: 5.6, end: 12.1, text: "第二段..." },
   ...
   ```

2. 复制这段代码到 `index.html` 的 `SUBTITLES` 数组。

3. 用 `ffprobe` 确认音频总时长：
   ```bash
   ffprobe -v quiet -show_entries format=duration -of csv=p=0 narration.wav
   ```

4. 将总时长 + 2~3 秒余量写入 `hyperframes.json` 的 `duration` 字段：
   ```json
   { "duration": 98 }
   ```

5. 将各场景的开始/结束时间与对应字幕段对齐。例如字幕段 3（start: 28s, end: 52s）对应场景 3，则：
   ```javascript
   master.set("#s3", { display: "flex" }, 28);
   master.set("#s3", { display: "none" }, 52);
   ```

### Step 3: HTML 编排

基于 `assets/template/` 中的模板创建项目。模板已包含正确的 HyperFrames 结构，只需填充：

1. 将 `assets/template/` 复制到目标目录
2. 修改 `hyperframes.json`：调整 `duration`（视频总时长 = 音频时长 + 2~3s）
3. 修改 `index.html`：
   - 添加场景 `<section class="scene">`，每个场景独立配色
   - 填入 `SUBTITLES` 数组（**必须来自 Step 2.5 的精确时间戳，禁止使用估算值**）
   - 编写场景切换逻辑（`master.set`）——每个场景的起止时间对齐对应字幕段边界
   - 编写文字动画（`master.fromTo`）
   - 字幕同步（`SUBTITLES.forEach` 部分已在模板中）
4. 放置 `narration.wav` 到项目根目录

模板结构详见 `assets/template/index.html` 中的注释。

### Step 4: Lint + 渲染

```bash
cd <project-dir>

# 方式 A：一键渲染（推荐，render.sh 包含 TTS + lint + render）
bash render.sh

# 方式 B：分步执行
bash render.sh tts              # 生成配音（narration.wav 已存在则跳过）
bash render.sh tts --force      # 强制重新生成配音
npx --yes hyperframes@0.6.56 lint
npx --yes hyperframes@0.6.56 render
```

**使用 `--force` 的场景**：当你更换了 TTS 引擎（如 edge-tts → 腾讯云）、修改了脚本文案、或怀疑当前 narration.wav 不是最新版本时。

输出：`renders/*.mp4`

## 关键规则（CRITICAL）

### HTML 结构强制要求

以下规则由 HyperFrames lint 强制检查，违反将导致渲染失败：

1. **Composition div 必须设置 `data-start="0"`**
   ```html
   <div data-composition-id="main" data-width="1920" data-height="1080" data-start="0">
   ```

2. **`<audio>` 元素必须在 composition 内部**
   ```html
   <audio id="narration" src="narration.wav" data-start="0"></audio>
   ```

3. **所有可视元素（字幕、场景）必须在 composition 内部**

4. **预览逻辑必须用 `window.__hf_rendering` 守卫**
   ```javascript
   if (typeof window.__hf_rendering === "undefined") {
     // 预览模式代码
   }
   ```

5. **预览中不操作 DOM `<audio>` 元素**——用 `new Audio()` 创建独立实例

完整错误修复指南见 `references/lint-errors.md`。

### 项目文件清单

| 文件 | 必须 | 说明 |
|------|------|------|
| `index.html` | ✅ | 视频画面编排（HTML+CSS+GSAP） |
| `hyperframes.json` | ✅ | 全局配置（分辨率/帧率/时长/音频） |
| `narration.wav` | ✅ | 旁白音频（由 tts.py --timed 生成） |
| `script.txt` | 推荐 | 脚本原始文案 |
| `tts.py` | 推荐 | TTS 配音脚本（复制自 Skill） |
| `.env.example` | 推荐 | TTS 凭据模板（客户自填） |
| `timeline.json` | 推荐 | 精确时间戳（tts.py --output-timestamps 生成） |
| `package.json` | 推荐 | npm scripts（lint/render） |
| `render.sh` | 推荐 | 一键渲染脚本（含 TTS + lint + render） |

### GSAP Timeline 命名规则

HyperFrames 通过 `window.__timelines` 发现动画时间轴：

```javascript
window.__timelines = {};
// timeline 键名必须与 composition data-composition-id 匹配
window.__timelines["composition-id"] = gsapTimeline;
```

### 场景切换模式

```javascript
// 精确时间点切换场景的 display 属性
// ⚠️ 时间点必须来自 Step 2.5 的精确字幕时间戳，禁止估算
master.set("#s1", { display: "flex" }, SCENE_START);
master.set("#s1", { display: "none" }, SCENE_END);
```

## 模板使用

`assets/template/` 包含一个完整的、lint 零错误的 HyperFrames 项目骨架。可以直接复制使用：

```
assets/template/
├── index.html          ← 含 GSAP Timeline 骨架、字幕系统、预览守卫
├── hyperframes.json    ← 1920×1080, 30fps 配置
├── package.json        ← lint/render/check scripts
├── render.sh           ← 一键渲染脚本（含 TTS + --force + 时长校验）
├── script.txt          ← 脚本占位文件
└── .env.example        ← TTS 凭据配置模板
```

在项目根目录还需放置：
- `scripts/tts.py` → 从 Skill 复制到项目目录：`cp ~/.workbuddy/skills/hyperframes-video/scripts/tts.py .`

模板中的 `index.html` 已包含：
- 正确的 composition 结构（`data-start="0"`）
- `<audio>` 元素在 composition 内部
- `__hf_rendering` 守卫的预览模式
- JS 动态创建的预览控件（避免 lint 误判）
- 字幕系统（`SUBTITLES.forEach` 自动同步）
- `window.__timelines` 注册

用户只需要填充：场景 HTML、CSS 样式、GSAP 动画、字幕数据（来自 Step 2.5 精确时间戳）。

## 渲染前检查清单

在 `npx hyperframes lint` 和 `render` 之前，逐项确认：

- [ ] `narration.wav` 是用 `--timed` 模式生成的最新版本（非旧缓存）
- [ ] `ffprobe` 确认的音频时长与 `hyperframes.json` 的 `duration` 一致（差值 < 3s）
- [ ] `SUBTITLES` 数组中的时间戳来自 `--output-timestamps` 输出，非手算估算
- [ ] 场景切换的 `master.set` 时间点对齐对应字幕段的 start/end 边界
- [ ] Composition div 有 `data-start="0"`
- [ ] `<audio>` 元素在 composition 内部
- [ ] 所有可视元素在 composition 内部
- [ ] JS 中使用 `window.__hf_rendering` 守卫包裹预览逻辑
- [ ] 预览音频使用 `new Audio()` 而非操作 DOM audio
- [ ] JS 字符串内容中**不含中文弯引号** `"` / `"` —— 用方括号 `[ ]` 或 ASCII 引号替代
- [ ] `renders/` 目录可写入
- [ ] TTS 凭据通过环境变量配置，**绝不硬编码**

## 设计建议

### 配色
- 每场景独立渐变背景，用颜色区分情绪
- 字幕条：半透明深色底 + `backdrop-filter: blur`
- 暖色系（橙/金/珊瑚）适合人物故事，冷色系适合科技/数据类

### 动画节奏
- 入场动画 duration 0.5–0.8s，配合旁白节奏
- 数据展示使用 `back.out` 缓动，营造冲击感
- 对话类场景使用左右交替淡入
- 不要在场景切换时堆叠过多动画

### 字幕样式
- 字号 34–42px（中文），确保手机端可读
- 底部位置，z-index 最高
- 半透明背景 + 圆角，与画面融合

## 跨平台发布

视频渲染完成后，可配合以下文案发布到短视频平台：

### 抖音 / 视频号
- 标题：15–25 字，设置悬念或提问
- 正文：2–3 句核心观点 + 互动引导
- 标签：3–5 个领域话题标签
- 封面：从结论场景截取大字标题画面

示例（低代码视频）：
> 标题：低代码平台，90% 的人都理解错了「易用」
> 正文：拖拽组件 ≠ 易用。真正的低代码，应该让开发者快速搞定复杂业务。
> #低代码 #无代码开发 #程序员 #科技干货

## 参考文档

- `references/lint-errors.md` — 所有 lint 错误及标准修复方案（含时间线错位）
- `references/workflow.md` — 五步工作流详细操作指南
