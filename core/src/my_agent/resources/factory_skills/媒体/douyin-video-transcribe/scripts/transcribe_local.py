#!/usr/bin/env python3



















import os
import sys
from pathlib import Path


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")



_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from transcribe import (                  
    check_dependencies,
    make_timestamp,
    validate_media_file,
    transcribe,
    write_cleaned_md,
)

check_dependencies(require_douyin=False)




OUTPUT_DIR = "."




def main():
    if len(sys.argv) < 2:
        print("用法: python transcribe_local.py <媒体文件路径> [--output OUTPUT_DIR]")
        print()
        print("示例:")
        print("  python scripts/transcribe_local.py video.mp4")
        print("  python scripts/transcribe_local.py audio.mp3 --output ./output")
        print()
        print("支持的视频格式: MP4, AVI, MKV, MOV, WMV, FLV, WEBM, M4V, TS")
        print("支持的音频格式: MP3, WAV, FLAC, M4A, OGG, AAC, WMA, OPUS")
        sys.exit(1)

    
    args = sys.argv[1:]
    output_dir = OUTPUT_DIR

    if "--output" in args:
        idx = args.index("--output")
        if idx + 1 < len(args):
            output_dir = args.pop(idx + 1)
        args.pop(idx)

    if not args:
        print("[ERROR] 请提供媒体文件路径")
        sys.exit(1)

    file_path = args[0]

    
    abs_path = validate_media_file(file_path)

    ts = make_timestamp()
    print(f"[Info] 时间戳: {ts}")
    print("[Info] 流程: Step1 验证文件 -> Step2 Whisper转录 -> Step3 整理输出")

    
    print("\n[Step 2/3] 正在转录（Whisper medium 模型，耗时取决于音频长度）...")
    result, txt_path, json_path = transcribe(abs_path, output_dir, timestamp=ts)

    raw_text = result["text"].strip()

    
    print("\n[Step 3/3] 转录完成，请 agent 整理后调用 write_cleaned_md() 写入 MD")
    print(f"RAW_TRANSCRIPT_START\n{raw_text}\nRAW_TRANSCRIPT_END")

    print("\n[Done] 转录完毕")
    print(f"  文本:   {txt_path}")
    print(f"  JSON:   {json_path}")
    print(f"  时间戳: {ts}")
    print(f"\n预览: {raw_text[:200]}...")

    
    return {
        "timestamp": ts,
        "source_path": abs_path,
        "source_name": os.path.basename(abs_path),
        "txt_path": txt_path,
        "json_path": json_path,
        "raw_text": raw_text,
        "segments": result["segments"],
    }


if __name__ == "__main__":
    main()
