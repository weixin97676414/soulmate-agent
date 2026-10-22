#!/usr/bin/env python3










import os
import sys
import json
import shutil
import time
from datetime import datetime


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def check_dependencies(require_douyin=False):





    
    core_deps = [
        ("whisper", "openai-whisper"),
        ("requests", "requests"),
        ("imageio_ffmpeg", "imageio[ffmpeg]"),
    ]

    
    optional_deps = [
        ("playwright", "playwright"),
    ]

    missing = []
    for mod_name, display in core_deps:
        try:
            __import__(mod_name)
        except ImportError as e:
            missing.append(f"  - {display}: {e}")

    if require_douyin:
        for mod_name, display in optional_deps:
            try:
                __import__(mod_name)
            except ImportError as e:
                missing.append(f"  - {display}: {e}")

    if missing:
        print("[ERROR] 缺少依赖包，请先运行环境配置脚本：")
        print("  python scripts/setup_env.py")
        if not require_douyin:
            print("  提示：本地转录模式只需核心依赖，抖音模式需额外安装 playwright")
        print()
        print("缺失项：")
        for m in missing:
            print(m)
        print()
        sys.exit(1)

    
    try:
        import torch
        _ = torch.__version__
    except Exception as e:
        print("[ERROR] torch 加载失败（Whisper 必需）")
        print(f"  错误: {e}")
        if "DLL load failed" in str(e) or "c10" in str(e):
            print("  可能原因: VC++ Redistributable 未安装")
            print("  下载: https://aka.ms/vs/17/release/vc_redist.x64.exe")
            print("  安装后可能需要重启系统")
        if "numpy" in str(e).lower():
            print("  可能原因: numpy >= 2 不兼容，需要 numpy < 2")
            print("  修复: pip install 'numpy<2' --force-reinstall")
        sys.exit(1)



def _get_whisper():
    import whisper
    return whisper




def make_timestamp() -> str:

    return datetime.now().strftime("%Y%m%d_%H%M%S")




def ensure_ffmpeg():

    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg_dir = os.path.dirname(ffmpeg_exe)
    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    ffmpeg_dest = os.path.join(ffmpeg_dir, "ffmpeg.exe")
    if not os.path.exists(ffmpeg_dest) and os.path.exists(ffmpeg_exe):
        shutil.copy(ffmpeg_exe, ffmpeg_dest)
    return ffmpeg_exe




def clean_corrupted_model_cache(model_name: str) -> bool:

    cache_dir = os.path.expanduser("~/.cache/whisper")
    model_path = os.path.join(cache_dir, f"{model_name}.pt")
    if os.path.exists(model_path):
        size = os.path.getsize(model_path)
        if size < 500_000_000:  
            print(f"[Whisper] 检测到疑似损坏的模型缓存 ({size/1024/1024:.0f}MB)，正在删除...")
            os.remove(model_path)
            print(f"[Whisper] 已删除 {model_path}")
            return True
    return False


def load_whisper_safe(model_name: str = "medium"):




    print(f"[Whisper] 加载模型: {model_name}（首次下载约 1.4GB）")

    
    clean_corrupted_model_cache(model_name)

    whisper = _get_whisper()
    try:
        model = whisper.load_model(model_name)
        return model
    except Exception as e:
        err_str = str(e)
        if "SIGABRT" in err_str or "corrupt" in err_str.lower() or "load" in err_str.lower():
            print(f"[Whisper] 模型加载失败 ({e})，可能是缓存损坏，正在清理后重试...")
            if clean_corrupted_model_cache(model_name):
                try:
                    model = whisper.load_model(model_name)
                    print("[Whisper] 重试成功")
                    return model
                except Exception as e2:
                    print(f"[Whisper] 重试仍然失败: {e2}")
                    raise
        raise


def _estimate_transcribe_time(duration_sec: float, device: str, model_name: str) -> str:











    if duration_sec <= 0:
        return "未知"

    
    multipliers = {
        ("cpu", "tiny"):   (0.2, 0.4),
        ("cpu", "base"):   (0.4, 0.7),
        ("cpu", "small"):  (0.8, 1.2),
        ("cpu", "medium"): (2.0, 3.0),
        ("cpu", "large"):  (5.0, 8.0),
        ("cuda", "tiny"):   (0.03, 0.05),
        ("cuda", "base"):   (0.05, 0.1),
        ("cuda", "small"):  (0.1, 0.2),
        ("cuda", "medium"): (0.15, 0.25),
        ("cuda", "large"):  (0.3, 0.5),
    }

    audio_min = duration_sec / 60.0
    key = (device, model_name)
    low_m, high_m = multipliers.get(key, (2.0, 3.0))  

    low = audio_min * low_m
    high = audio_min * high_m

    if high < 1:
        return f"约 {int(low*60)}-{int(high*60)} 秒"
    elif high < 5:
        return f"约 {low:.0f}-{high:.0f} 分钟"
    else:
        low_str = f"{low:.0f}" if low == int(low) else f"{low:.1f}"
        high_str = f"{high:.0f}" if high == int(high) else f"{high:.1f}"
        return f"约 {low_str}-{high_str} 分钟"


def _get_media_duration(media_path: str) -> float:

    import subprocess
    try:
        import imageio_ffmpeg
        ffprobe_exe = imageio_ffmpeg.get_ffmpeg_exe().replace("ffmpeg", "ffprobe")
        if not os.path.exists(ffprobe_exe):
            
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            result = subprocess.run(
                [ffmpeg_exe, "-i", media_path, "-f", "null", "-"],
                capture_output=True, text=True, timeout=30,
            )
            
            for line in result.stderr.splitlines():
                if "Duration" in line:
                    
                    dur_str = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = dur_str.split(":")
                    return float(h) * 3600 + float(m) * 60 + float(s)
            return 0

        result = subprocess.run(
            [ffprobe_exe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", media_path],
            capture_output=True, text=True, timeout=30,
        )
        dur = float(result.stdout.strip())
        return dur if dur > 0 else 0
    except Exception:
        return 0


def _format_duration(seconds: float) -> str:

    if seconds <= 0:
        return "未知"
    m = int(seconds // 60)
    s = int(seconds % 60)
    if m > 0:
        return f"{m}分{s}秒"
    return f"{s}秒"





WHISPER_MODEL = "medium"
WHISPER_LANGUAGE = "zh"
WHISPER_INITIAL_PROMPT = "以下是普通话的句子。"  


def transcribe(
    media_path: str,
    output_dir: str = ".",
    timestamp: str = "",
    model_name: str | None = None,
    language: str | None = None,
    initial_prompt: str | None = None,
) -> tuple[dict, str, str]:














    model_name = model_name or WHISPER_MODEL
    language = language or WHISPER_LANGUAGE
    initial_prompt = initial_prompt or WHISPER_INITIAL_PROMPT

    ffmpeg_path = ensure_ffmpeg()
    print(f"[转录] ffmpeg: {ffmpeg_path}")

    
    device = "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
            print(f"[转录] GPU 加速: CUDA {torch.cuda.get_device_name(0)}")
        else:
            print("[转录] GPU: 不可用，使用 CPU（较慢）")
    except Exception:
        print("[转录] GPU: torch 未安装，使用 CPU")

    
    duration = _get_media_duration(media_path)
    if duration > 0:
        print(f"[转录] 媒体时长: {_format_duration(duration)}")
        est = _estimate_transcribe_time(duration, device, model_name)
        print(f"[转录] 预估耗时: {est} (模型={model_name}, 设备={device})")
    else:
        print("[转录] 媒体时长: 无法获取")

    
    model = load_whisper_safe(model_name)

    print(f"[转录] ========== 开始转录 ========== ")

    
    start_time = time.time()

    print(f"[转录] 处理中: {os.path.basename(media_path)}")

    result = model.transcribe(
        media_path,
        language=language,
        verbose=True,
        task="transcribe",
        initial_prompt=initial_prompt,
    )

    elapsed = time.time() - start_time
    print(f"[转录] ========== 转录完成 ========== ")
    print(f"[转录] 实际耗时: {_format_duration(elapsed)}")
    if duration > 0 and elapsed > 0:
        ratio = elapsed / duration
        print(f"[转录] 转录速度: {ratio:.1f}x 音频时长 ({device}/{model_name})")

    
    suffix = f"_{timestamp}" if timestamp else ""
    transcript_txt_path = os.path.join(output_dir, f"transcript{suffix}.txt")
    transcript_json_path = os.path.join(output_dir, f"transcript{suffix}.json")

    
    with open(transcript_txt_path, "w", encoding="utf-8") as f:
        f.write("=== 完整文字稿 ===\n\n")
        f.write(result["text"].strip())
        f.write("\n\n=== 带时间戳分段 ===\n\n")
        for seg in result["segments"]:
            start = seg["start"]
            end = seg["end"]
            text = seg["text"].strip()
            start_str = f"{int(start//60):02d}:{start%60:05.2f}"
            end_str = f"{int(end//60):02d}:{end%60:05.2f}"
            f.write(f"[{start_str} --> {end_str}]  {text}\n")

    
    with open(transcript_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[转录] 已保存: {transcript_txt_path}")
    print(f"[转录] 已保存: {transcript_json_path}")
    char_count = len(result['text'].replace(' ', '').replace('\n', '').strip())
    print(f"[转录] 共 {char_count} 字, {len(result['segments'])} 段")
    return result, transcript_txt_path, transcript_json_path




def write_cleaned_md(
    cleaned_text: str,
    source: str,
    source_type: str = "douyin",
    timestamp: str = "",
    output_dir: str = ".",
) -> str:
















    suffix = f"_{timestamp}" if timestamp else ""
    md_path = os.path.join(output_dir, f"transcript{suffix}.md")

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if source_type == "local":
        title = "# 媒体文件转录文本"
        meta = (
            f"> **源文件：** {source}\n"
            f"> **转录时间：** {date_str}\n"
            f"> **说明：** 本文由 Whisper 语音识别后经整理纠错，原文内容未做删改。"
        )
    else:
        title = "# 抖音视频转录文本"
        meta = (
            f"> **来源：** {source}\n"
            f"> **转录时间：** {date_str}\n"
            f"> **说明：** 本文由 Whisper 语音识别后经整理纠错，原文内容未做删改。"
        )

    footer = "*由 douyin-video-transcribe 技能自动生成*"

    md_content = f"{title}\n\n{meta}\n\n---\n\n{cleaned_text}\n\n---\n\n{footer}\n"

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"[MD] 已保存整理后 Markdown: {md_path}")
    return md_path




SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts",
}

SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma", ".opus",
}

SUPPORTED_EXTENSIONS = SUPPORTED_VIDEO_EXTENSIONS | SUPPORTED_AUDIO_EXTENSIONS


def validate_media_file(file_path: str) -> str:



    if not os.path.exists(file_path):
        print(f"[ERROR] 文件不存在: {file_path}")
        sys.exit(1)

    abs_path = os.path.abspath(file_path)
    ext = os.path.splitext(abs_path)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS:
        print(f"[ERROR] 不支持的格式: {ext}")
        print(f"  支持的视频格式: {', '.join(sorted(SUPPORTED_VIDEO_EXTENSIONS))}")
        print(f"  支持的音频格式: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}")
        sys.exit(1)

    file_type = "视频" if ext in SUPPORTED_VIDEO_EXTENSIONS else "音频"
    size_mb = os.path.getsize(abs_path) / 1024 / 1024
    print(f"[文件] {file_type}: {os.path.basename(abs_path)} ({size_mb:.1f} MB)")
    return abs_path
