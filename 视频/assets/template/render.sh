#!/usr/bin/env bash
# HyperFrames 一键渲染脚本
# ===========================================
# 用法:
#   bash render.sh                # 全部：TTS + lint + render
#   bash render.sh tts            # 仅生成配音（narration.wav 已存在则跳过）
#   bash render.sh tts --force    # 强制重新生成配音（删除旧文件后生成）
#   bash render.sh lint           # 仅代码检查
#   bash render.sh render         # 仅渲染（跳过 TTS）
#   bash render.sh check          # lint + render
# ===========================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

HF_VERSION="${HF_VERSION:-0.6.56}"
FORCE_TTS=false

# 解析 --force / --regen 子参数
for arg in "$@"; do
  case "$arg" in
    --force|--regen|--regen-tts) FORCE_TTS=true ;;
  esac
done

# ==== Step 1: TTS 配音 ====
do_tts() {
  echo ""
  echo "════════════════════════════════════════"
  echo "  Step 1: TTS 配音"
  echo "════════════════════════════════════════"
  echo ""

  if [ -f narration.wav ] && [ "$FORCE_TTS" != true ]; then
    echo "⚠️  narration.wav 已存在，跳过 TTS。"
    echo "   如需强制重新生成: bash render.sh tts --force"
    echo ""
    # 验证音频时长与 hyperframes.json 一致性
    if command -v ffprobe &>/dev/null && [ -f hyperframes.json ]; then
      AUDIO_DUR=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 narration.wav 2>/dev/null | cut -d. -f1)
      JSON_DUR=$(python3 -c "import json; print(int(json.load(open('hyperframes.json'))['duration']))" 2>/dev/null || echo "0")
      if [ -n "$AUDIO_DUR" ] && [ "$JSON_DUR" != "0" ]; then
        DIFF=$(( AUDIO_DUR - JSON_DUR ))
        DIFF_ABS=${DIFF#-}
        if [ "$DIFF_ABS" -gt 5 ]; then
          echo "⚠️  警告: 音频时长 (${AUDIO_DUR}s) 与 hyperframes.json 中的 duration (${JSON_DUR}s) 差距 ${DIFF_ABS}s！"
          echo "   时间线可能不匹配。建议: bash render.sh tts --force 重新生成音频，并更新 hyperframes.json。"
        fi
      fi
    fi
    return
  fi

  if [ "$FORCE_TTS" = true ]; then
    echo "🔄 --force：删除旧的 narration.wav 重新生成..."
    rm -f narration.wav
  fi

  if [ ! -f tts.py ]; then
    echo "⚠️  tts.py 不存在。请从 Skill 复制到项目目录："
    echo "    cp ~/.workbuddy/skills/hyperframes-video/scripts/tts.py ."
    return 1
  fi

  # 默认使用 edge-tts（免费），客户可设置 TTS_PROVIDER=tencent 切换
  # 腾讯云凭据通过环境变量配置，详见 .env.example
  # --timed 精确计时模式：逐段测量实际时长（推荐）
  python3 tts.py --timed --output-timestamps timeline.json script.txt narration.wav

  echo ""
  echo "📋 时间戳已写入 timeline.json，请将输出中的 JS 代码段复制到 index.html 的 SUBTITLES 数组。"
}

# ==== Step 2: Lint ====
do_lint() {
  echo ""
  echo "════════════════════════════════════════"
  echo "  Step 2: Lint 检查"
  echo "════════════════════════════════════════"
  echo ""
  npx --yes "hyperframes@${HF_VERSION}" lint
}

# ==== Step 3: Render ====
do_render() {
  echo ""
  echo "════════════════════════════════════════"
  echo "  Step 3: 渲染出片"
  echo "════════════════════════════════════════"
  echo ""

  if [ ! -f narration.wav ]; then
    echo "❌ narration.wav 不存在，请先运行: bash render.sh tts"
    return 1
  fi

  mkdir -p renders
  npx --yes "hyperframes@${HF_VERSION}" render
  echo ""
  echo "✅ 渲染完成！输出目录: ${SCRIPT_DIR}/renders/"
  ls -lh renders/*.mp4 2>/dev/null || echo "  (未找到 .mp4 文件，请检查日志)"
}

# ==== 主流程 ====
CMD="${1:-all}"
case "$CMD" in
  tts)
    do_tts
    ;;
  lint)
    do_lint
    ;;
  render)
    do_render
    ;;
  check)
    do_lint
    do_render
    ;;
  all)
    do_tts
    do_lint
    do_render
    ;;
  --force|--regen|--regen-tts)
    echo "用法: bash render.sh [tts|lint|render|check|all] [--force]"
    echo "  --force  仅用于 tts 子命令，强制重新生成配音"
    exit 1
    ;;
  *)
    echo "用法: bash render.sh [tts|lint|render|check|all] [--force]"
    exit 1
    ;;
esac
