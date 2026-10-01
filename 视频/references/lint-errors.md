# HyperFrames Lint 常见错误与修复方案

本文档汇总 HyperFrames `lint` 检查中反复出现的问题及标准修复方法。

---

## Error 1: Root Composition 误判

**错误信息**：`"#preview-controls" (or similar id) treated as root composition`

**原因**：HyperFrames lint 将 composition div 之外的任何 div 也当作潜在的 composition 来解析。如果 HTML 中有预览控件、加载指示器等 UI 元素放在 composition 外部，lint 会尝试将它们解析为 composition 并报错。

**修复方案**：
- **方案 A（推荐）**：将预览控件完全移除 HTML，改为在 JS 中动态创建（用 `document.createElement` + `appendChild`）
- **方案 B**：将所有 UI 元素移入 composition div 内部

```javascript
// ✅ 正确：JS 动态创建预览控件
if (typeof window.__hf_rendering === "undefined") {
  var ctrl = document.createElement("div");
  ctrl.id = "preview-ctrl";
  ctrl.innerHTML = "...";
  document.body.appendChild(ctrl);
}
```

```html
<!-- ❌ 错误：预览控件在 composition 外部 -->
<div data-composition-id="main">...</div>
<div id="preview-controls">...</div>
```

---

## Error 2: Missing `<audio>` Element

**错误信息**：`No <audio> element found; render will be silent`

**原因**：`hyperframes.json` 中配置了 `audioSources`，但 HTML 中没有对应的 `<audio>` 标签。

**修复方案**：在 composition div 内部第一行添加 `<audio>` 元素。

```html
<div data-composition-id="main" data-width="1920" data-height="1080" data-start="0">
  <audio id="narration" src="narration.wav" data-start="0"></audio>
  ...
</div>
```

**注意**：`data-start="0"` 是必需的。

---

## Error 3: Missing `data-start="0"` on Composition

**错误信息**：Composition div 缺少 `data-start` 属性

**原因**：HyperFrames 要求 composition div 明确声明起始时间。

**修复方案**：在 composition div 上添加 `data-start="0"`。

```html
<!-- ✅ 正确 -->
<div data-composition-id="main" data-width="1920" data-height="1080" data-start="0">

<!-- ❌ 错误 -->
<div data-composition-id="main" data-width="1920" data-height="1080">
```

---

## Error 4: Imperative Audio Control

**错误信息**：JS 中直接操作 `<audio>` DOM 元素（`.play()`, `.pause()`, `.currentTime` 等）

**原因**：HyperFrames 渲染时需要独占音频控制权，JS 中对 `<audio>` 元素的命令式操作会干扰渲染管线。

**修复方案**：
- 预览模式用 `window.__hf_rendering` 守卫包裹所有音频操作
- 预览中不用 HTML 中的 `<audio>` 元素，而是用 `new Audio()` 创建独立的 Audio 实例

```javascript
// ✅ 正确：用守卫 + 独立 Audio 实例
if (typeof window.__hf_rendering === "undefined") {
  var narrationAudio = new Audio("narration.wav");
  narrationAudio.play().catch(function(){});
}
```

```javascript
// ❌ 错误：直接操作 DOM audio 元素
var audio = document.getElementById("narration");
audio.play();
```

---

## Warning: Font Fallback（非阻塞）

**警告信息**：`Font family "XXX" not found, using fallback`

**原因**：HTML 中使用的字体在渲染环境中不可用。

**影响**：非阻塞警告，不影响渲染。视频将使用系统回退字体。

**修复方案**（可选）：
1. 使用通用字体族（sans-serif, serif）
2. 在 CSS 中提供完整的 fallback 链：`font-family: "Custom Font", "PingFang SC", "Microsoft YaHei", sans-serif;`

---

## Error 5: Sandbox 写入权限（渲染阶段）

**错误信息**：`EACCES: permission denied, mkdir 'renders/...'`

**原因**：HyperFrames 渲染时需要创建临时目录和写入帧图片、最终 MP4。在沙箱环境（如 WorkBuddy 的 Bash 工具）中可能被阻止。

**修复方案**：
- 确保 `renders/` 目录存在：`mkdir -p renders/`
- 如果沙箱阻止，在用户本地终端执行渲染命令
- 清除旧的 `renders/work-*` 临时目录（渲染失败残留）

```bash
# 清理失败的渲染残留
rm -rf renders/work-*

# 确保 renders 目录存在
mkdir -p renders
```

---

---

## Error 6: 中文弯引号导致 JS 语法错误

**错误信息**：`invalid_inline_script_syntax: Unexpected identifier '易用'`（或任意中文词）

**原因**：JS 字符串内容中出现了中文弯引号 `"` / `"`（U+201C / U+201D），被解析器当作 JS 字符串边界，导致随后的中文词变成裸标识符而报语法错。

**常见场景**：字幕数组 `text` 字段中的引用写法，如：
```javascript
{ text: "什么是"易用"？" }   // ❌ 弯引号嵌套在 ASCII 双引号里，打破字符串边界
```

**修复方案**：
1. 将内层弯引号改为方括号或直引号：
```javascript
{ text: "什么是[易用]？" }   // ✅ 方括号替代
{ text: '什么是"易用"？' }   // ✅ 换用单引号包裹外层
```
2. 在写 JS 字符串时，全程只用 ASCII 直引号（`'` / `"`），弯引号仅用于 HTML 文本节点内容。

---

## Error 7: TTS 写入时被沙箱拦截 + narration.wav 不在目录

**错误信息**：
- `audio_src_not_found: <audio> element references file(s) not found`（lint 阶段）
- `PermissionError: Operation not permitted`（TTS 生成阶段）

**根因分析**：

WorkBuddy 沙箱对跨工作区目录有严格的扩展名写入限制。当 AI 助手在当前工作区（如 `2026-06-01-15-14-05`）运行，而项目在另一工作区（如 `2026-05-29-13-16-31/hyperframes-demo/`）时，写入 `.wav` 文件会被阻止。

**自动化解决方案（推荐）**：

项目目录下的 `render.sh` 已内置 TTS 生成步骤，在用户本地终端执行即可，无需 AI 助手操作文件：

```bash
# 用户本地终端：一键生成配音 + lint + 渲染
cd /path/to/project
bash render.sh

# 或分步执行
python3 tts.py script.txt narration.wav    # Step 1: TTS
npx hyperframes lint                        # Step 2: Lint
npx hyperframes render                      # Step 3: Render
```

**AI 助手操作指南**：

1. 将 `narration.wav` 写入当前工作区 `$PWD/`（而非项目目录）
2. 通过附件系统传递给用户
3. 用户本地终端 `cp /path/to/narration.wav project/` 放置文件
4. 告知用户：这是最后一次手动操作，后续 `render.sh` 会自动生成

**防止复发**：
- 在 Skill 的 Step 2 中明确：TTS 输出优先写入当前工作区
- `render.sh` 包含完整的 TTS → lint → render 流水线
- 模板文件 `.env.example` 引导客户自行配置凭据
- 用 `bash render.sh tts --force` 强制重新生成，避免使用旧缓存文件

---

## Error 8: TTS 音频时长与 HTML 时间线不匹配（渲染后可见）

**症状**：
- 视频渲染成功，但后半段字幕与音频严重不同步
- 音频还在播放，字幕已经提前结束（或反之）
- 场景切换时画面已变，但配音还在上一段

**根因分析**：

`tts.py` 中的估算公式 `dur = max(2.5, len(line) / 3.8)` 与实际 API 音频时长之间存在系统性偏差。

| 引擎 | 典型偏差 | 方向 |
|------|---------|------|
| edge-tts | 15–25% | 低估（实际更长） |
| 腾讯云 TTS | 5–15% | 高估或低估 |

**避免方法**：

1. **始终使用 `--timed` 模式生成 TTS**：
   ```bash
   python3 tts.py --timed --output-timestamps timeline.json script.txt narration.wav
   ```

2. **禁止将估算时间戳直接写入 HTML**。`SUBTITLES` 数组和场景切换时间点必须来自 `--timed` 的输出。

3. **渲染前验证**：
   ```bash
   # 确认音频时长
   AUDIO_DUR=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 narration.wav | cut -d. -f1)
   # 确认 JSON duration
   JSON_DUR=$(python3 -c "import json; print(int(json.load(open('hyperframes.json'))['duration']))")
   # 差值应 < 3s
   echo "音频: ${AUDIO_DUR}s, JSON: ${JSON_DUR}s"
   ```

4. **重新生成时强制覆盖旧文件**：
   ```bash
   bash render.sh tts --force   # 删除旧 narration.wav 重新生成
   ```

---

## 检查清单（渲染前必查）

在 `npx hyperframes lint` 和 `render` 之前，逐项确认：

- [ ] **`narration.wav` 是用 `--timed` 模式生成的最新版本**（非旧缓存，非估算时长版本）
- [ ] **`ffprobe` 音频时长与 `hyperframes.json` duration 一致**（差值 < 3s）
- [ ] **`SUBTITLES` 数组时间戳来自 `--output-timestamps` 输出**，禁止手算估算
- [ ] **场景切换时间点对齐对应字幕段 start/end 边界**
- [ ] Composition div 有 `data-start="0"`
- [ ] `<audio>` 元素在 composition 内部
- [ ] 所有可视元素在 composition 内部
- [ ] JS 中使用 `window.__hf_rendering` 守卫包裹预览逻辑
- [ ] 预览音频使用 `new Audio()` 而非操作 DOM audio
- [ ] `renders/` 目录可写入
- [ ] JS 字符串内容中**不含中文弯引号** `"` / `"` —— 用方括号 `[ ]` 或 ASCII 引号替代
- [ ] TTS 凭据通过环境变量配置，**绝不硬编码**
- [ ] 如需重新生成音频：`bash render.sh tts --force`
