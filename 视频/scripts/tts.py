#!/usr/bin/env python3
"""
HyperFrames TTS 配音生成器
===========================
  模式 1 - edge-tts（免费，零配置）:
    python3 tts.py script.txt narration.wav

  模式 2 - 腾讯云 TTS（客户自配凭据）:
    export TTS_PROVIDER=tencent
    export TENCENT_SECRET_ID=AKIDxxxxx
    export TENCENT_SECRET_KEY=xxxxxxxx
    python3 tts.py script.txt narration.wav

  ⚠️ 所有凭据从环境变量读取，绝不硬编码。

  精确计时模式（--timed）:
    python3 tts.py --timed --output-timestamps timeline.json script.txt narration.wav
    逐段生成音频 → 测量每段实际时长 → 输出精确时间戳 JSON
    解决「估算时长 ≠ 实际音频时长」导致的字幕错位问题。

  ⚠️ --timed 模式下 --output-timestamps 为必选项，时间戳将写入指定 JSON 文件。
"""

import sys, os, json, re, hashlib, hmac, time, struct, argparse, tempfile, wave
from datetime import datetime, timezone

# ---- 配置（全部从环境变量读取）----
TTS_PROVIDER   = os.environ.get("TTS_PROVIDER", "edge").lower()
TTS_VOICE      = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
TTS_RATE       = os.environ.get("TTS_RATE", "+5%")
TTS_VOICE_TYPE = int(os.environ.get("TTS_VOICE_TYPE", "101030"))  # 智柯
TTS_SAMPLE_RATE = int(os.environ.get("TTS_SAMPLE_RATE", "16000"))

TENCENT_ID  = os.environ.get("TENCENT_SECRET_ID", "")
TENCENT_KEY = os.environ.get("TENCENT_SECRET_KEY", "")


# ---- 脚本解析 ----
def parse_script(filepath: str) -> list[dict]:
    segs = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("//") or line.startswith("#"):
                continue
            # 去除行末场景注释
            line = re.sub(r"\s*//\s*场景.*", "", line).strip()
            # 去除方括号/书名号标记标题
            line = re.sub(r"^[【\[].*?[】\]]\s*", "", line)
            if line:
                dur = max(2.5, len(line) / 3.8)  # 中速估算（非 timed 模式使用）
                segs.append({"text": line, "dur_est": dur})
    return segs


def print_timestamps(segs: list[dict], start: float = 0.5, gap: float = 0.35):
    """输出预估时间戳（非 timed 模式）"""
    t = start
    entries = []
    for s in segs:
        entries.append({"start": round(t, 1), "end": round(t + s.get("dur_actual", s["dur_est"]), 1), "text": s["text"]})
        t += s.get("dur_actual", s["dur_est"]) + gap
    print(json.dumps(entries, ensure_ascii=False, indent=2))
    print(f"\n⏱ {'实测' if 'dur_actual' in segs[0] else '预估'}总时长: {t:.1f}s | 段落数: {len(segs)}", file=sys.stderr)
    return entries


def wav_duration_from_bytes(pcm_bytes: bytes, sample_rate: int) -> float:
    """从原始 PCM 字节数计算实际时长（16-bit mono）"""
    return len(pcm_bytes) / (sample_rate * 2)


def write_wav(pcm_bytes: bytes, filepath: str, sample_rate: int):
    """写入标准 WAV 文件"""
    num_samples = len(pcm_bytes) // 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm_bytes), b"WAVE", b"fmt ", 16,
        1, 1, sample_rate, sample_rate * 2, 2, 16,
        b"data", len(pcm_bytes),
    )
    with open(filepath, "wb") as f:
        f.write(header + pcm_bytes)


def concat_wavs(wav_files: list[str], output_file: str):
    """将多个 WAV 文件拼接为一个（要求相同参数）"""
    import shutil
    if len(wav_files) == 1:
        shutil.copy2(wav_files[0], output_file)
        return
    # 读取第一个文件获取参数
    with wave.open(wav_files[0], "rb") as w0:
        params = w0.getparams()
        combined = w0.readframes(w0.getnframes())
    for wf in wav_files[1:]:
        with wave.open(wf, "rb") as w:
            combined += w.readframes(w.getnframes())
    with wave.open(output_file, "wb") as out:
        out.setparams(params)
        out.writeframes(combined)


# ---- Provider: edge-tts（免费）----
def tts_edge(input_file: str, output_file: str, timed: bool = False):
    try:
        import edge_tts
    except ImportError:
        print("请先安装: pip install edge-tts"); sys.exit(1)

    segs = parse_script(input_file)
    if not segs:
        print("脚本为空"); sys.exit(1)

    print(f"🎙️  edge-tts | {TTS_VOICE} | 语速:{TTS_RATE} | {len(segs)}段")
    if timed:
        print("   ⏱ 精确计时模式：逐段测量实际时长\n")
    else:
        print("")

    import asyncio

    async def _gen():
        if timed:
            # 精确计时：逐段生成 WAV → 测量时长 → 拼接
            import subprocess as sp
            seg_wavs = []
            seg_durations = []

            for i, s in enumerate(segs):
                print(f"  [{i+1}/{len(segs)}] {s['text'][:50]}")
                comm = edge_tts.Communicate(s["text"], TTS_VOICE, rate=TTS_RATE)
                mp3_data = b""
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        mp3_data += chunk["data"]

                # 转 WAV 并测量时长
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
                    tf.write(mp3_data); mp3_tmp = tf.name

                wav_tmp = tempfile.mktemp(suffix=".wav")
                r = sp.run(["ffmpeg", "-y", "-i", mp3_tmp, "-acodec", "pcm_s16le",
                            "-ar", str(TTS_SAMPLE_RATE), "-ac", "1", wav_tmp],
                           check=True, capture_output=True)
                os.unlink(mp3_tmp)

                # 测量实际时长
                with wave.open(wav_tmp, "rb") as wf:
                    actual_dur = wf.getnframes() / wf.getframerate()
                seg_durations.append(actual_dur)
                seg_wavs.append(wav_tmp)
                print(f"       ⏱ 实测 {actual_dur:.1f}s (估算 {s['dur_est']:.1f}s)")

            # 拼接
            concat_wavs(seg_wavs, output_file)

            # 清理临时文件
            for wf in seg_wavs:
                os.unlink(wf)

            for i, d in enumerate(seg_durations):
                segs[i]["dur_actual"] = d

            return segs

        else:
            # 快速模式：合并所有段一次生成
            all_mp3 = b""
            for i, s in enumerate(segs):
                print(f"  [{i+1}/{len(segs)}] {s['text'][:50]}")
                comm = edge_tts.Communicate(s["text"], TTS_VOICE, rate=TTS_RATE)
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        all_mp3 += chunk["data"]

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
                tf.write(all_mp3); tmp = tf.name

            import subprocess as sp
            sp.run(["ffmpeg", "-y", "-i", tmp, "-acodec", "pcm_s16le",
                    "-ar", str(TTS_SAMPLE_RATE), "-ac", "1", output_file],
                   check=True, capture_output=True)
            os.unlink(tmp)
            return segs

    segs = asyncio.get_event_loop().run_until_complete(_gen())

    size_mb = os.path.getsize(output_file) / 1024 / 1024
    print(f"\n✅ {output_file} ({size_mb:.1f} MB)")
    return segs


# ---- Provider: 腾讯云 TTS（API v3, TC3-HMAC-SHA256）----
def tts_tencent(input_file: str, output_file: str, timed: bool = False):
    if not TENCENT_ID or not TENCENT_KEY:
        print("=" * 55)
        print("❌ 腾讯云 TTS 需设置环境变量:\n")
        print("  export TENCENT_SECRET_ID=AKIDxxxxxxxx")
        print("  export TENCENT_SECRET_KEY=xxxxxxxxxxxx")
        print("\n  凭据: https://console.cloud.tencent.com/cam/capi")
        print("  或直接用免费 edge-tts: unset TTS_PROVIDER")
        print("=" * 55)
        sys.exit(1)

    segs = parse_script(input_file)
    if not segs:
        print("脚本为空"); sys.exit(1)

    import urllib.request, base64

    svc, host, action, version, region = "tts", "tts.tencentcloudapi.com", "TextToVoice", "2019-08-23", "ap-guangzhou"
    endpoint = f"https://{host}/"

    print(f"🎙️  腾讯云 TTS | 音色:{TTS_VOICE_TYPE} | 采样率:{TTS_SAMPLE_RATE}Hz")
    if timed:
        print("   ⏱ 精确计时模式：逐段测量实际时长\n")
    else:
        print(f"   {len(segs)}段\n")

    seg_durations = []
    seg_wavs = []

    for i, s in enumerate(segs):
        text = s["text"]
        print(f"  [{i+1}/{len(segs)}] {text[:50]}")

        payload = json.dumps({
            "Text": text,
            "SessionId": f"hf-{int(time.time()*1000)}-{i}",
            "VoiceType": TTS_VOICE_TYPE,
            "Codec": "wav",
            "SampleRate": TTS_SAMPLE_RATE,
            "Speed": 0,
            "Volume": 0,
            "PrimaryLanguage": 1,
        })

        # TC3-HMAC-SHA256 签名
        ts = int(time.time())
        date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

        canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{host}\nx-tc-action:{action.lower()}\n"
        signed_headers = "content-type;host;x-tc-action"
        hashed_payload = hashlib.sha256(payload.encode()).hexdigest()
        canonical_request = f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"

        credential_scope = f"{date_str}/{svc}/tc3_request"
        hashed_canonical = hashlib.sha256(canonical_request.encode()).hexdigest()
        string_to_sign = f"TC3-HMAC-SHA256\n{ts}\n{credential_scope}\n{hashed_canonical}"

        def _sign(key, msg):
            return hmac.new(key, msg.encode(), hashlib.sha256).digest()

        k_date = _sign(("TC3" + TENCENT_KEY).encode(), date_str)
        k_svc  = _sign(k_date, svc)
        k_sign = _sign(k_svc, "tc3_request")
        sig    = hmac.new(k_sign, string_to_sign.encode(), hashlib.sha256).hexdigest()

        auth = f"TC3-HMAC-SHA256 Credential={TENCENT_ID}/{credential_scope}, SignedHeaders={signed_headers}, Signature={sig}"

        req = urllib.request.Request(endpoint, data=payload.encode(),
            headers={
                "Authorization": auth,
                "Content-Type": "application/json; charset=utf-8",
                "Host": host,
                "X-TC-Action": action,
                "X-TC-Timestamp": str(ts),
                "X-TC-Version": version,
                "X-TC-Region": region,
            })

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                r = json.loads(resp.read())
            if "Response" in r and "Audio" in r["Response"]:
                pcm_bytes = base64.b64decode(r["Response"]["Audio"])
                actual_dur = wav_duration_from_bytes(pcm_bytes, TTS_SAMPLE_RATE)
                seg_durations.append(actual_dur)

                if timed:
                    print(f"       ⏱ 实测 {actual_dur:.1f}s (估算 {s['dur_est']:.1f}s)")
                    # 写入独立 WAV 以便后续拼接
                    wav_tmp = tempfile.mktemp(suffix=".wav")
                    write_wav(pcm_bytes, wav_tmp, TTS_SAMPLE_RATE)
                    seg_wavs.append(wav_tmp)
                else:
                    seg_wavs.append(pcm_bytes)  # 存原始 PCM 字节
            elif "Response" in r and "Error" in r["Response"]:
                err = r["Response"]["Error"]
                print(f"     ❌ {err.get('Code','?')}: {err.get('Message','?')}")
            else:
                print(f"     ⚠️ {json.dumps(r, ensure_ascii=False)[:200]}")
        except Exception as e:
            print(f"     ❌ 网络错误: {e}")

    # 写入最终文件
    if not seg_wavs:
        print("\n❌ 未获取到任何音频数据"); sys.exit(1)

    if timed:
        # timed 模式：拼接已有 WAV
        concat_wavs(seg_wavs, output_file)
        for wf in seg_wavs:
            os.unlink(wf)
    else:
        # 非 timed：直接拼接 PCM 并写 WAV
        all_pcm = b"".join(seg_wavs)
        write_wav(all_pcm, output_file, TTS_SAMPLE_RATE)

    for i, d in enumerate(seg_durations):
        segs[i]["dur_actual"] = d

    size_mb = os.path.getsize(output_file) / 1024 / 1024
    print(f"\n✅ {output_file} ({size_mb:.1f} MB)")
    return segs


# ---- 入口 ----
def main():
    parser = argparse.ArgumentParser(description="HyperFrames TTS 配音生成器")
    parser.add_argument("script", help="脚本文件（script.txt）")
    parser.add_argument("output", help="输出音频文件（narration.wav）")
    parser.add_argument("--timed", action="store_true",
                        help="精确计时模式：逐段生成音频并测量实际时长（推荐用于生产）")
    parser.add_argument("--output-timestamps", metavar="FILE",
                        help="输出精确时间戳 JSON 到指定文件（计时模式下推荐）")
    parser.add_argument("--gap", type=float, default=0.35,
                        help="段落间隔时间（秒，默认 0.35）")
    parser.add_argument("--start-offset", type=float, default=0.5,
                        help="第一条字幕起始偏移（秒，默认 0.5）")

    args = parser.parse_args()

    if args.timed and not args.output_timestamps:
        print("⚠️  精确计时模式建议同时指定 --output-timestamps 以保存时间戳。")
        print("   示例: --timed --output-timestamps timeline.json\n")

    print(f"📄 脚本: {args.script}  →  🎵 {args.output}")
    print(f"🔧 引擎: {TTS_PROVIDER}")

    if TTS_PROVIDER == "tencent":
        segs = tts_tencent(args.script, args.output, timed=args.timed)
    else:
        segs = tts_edge(args.script, args.output, timed=args.timed)

    entries = print_timestamps(segs, start=args.start_offset, gap=args.gap)

    if args.output_timestamps:
        with open(args.output_timestamps, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        print(f"📋 时间戳已写入: {args.output_timestamps}", file=sys.stderr)
        print(f"📋 复制以下 JS 代码到 index.html 的 SUBTITLES 数组:", file=sys.stderr)
        print("=" * 55, file=sys.stderr)
        for e in entries:
            print(f'  {{ index: 0, start: {e["start"]:.1f}, end: {e["end"]:.1f}, text: "{e["text"]}" }},', file=sys.stderr)
        print("=" * 55, file=sys.stderr)


if __name__ == "__main__":
    main()
