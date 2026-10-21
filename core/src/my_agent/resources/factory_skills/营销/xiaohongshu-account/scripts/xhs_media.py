# -*- coding: utf-8 -*-












from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from xhs_common import SKILL_DIR, RateLimiter, human_num, log, write_json

limiter = RateLimiter(0.6, 1.6)
REFERER = "https://www.xiaohongshu.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _save(url: str, dest: Path) -> bool:
    if not url or dest.exists():
        return dest.exists()
    dest.parent.mkdir(parents=True, exist_ok=True)
    limiter.wait()
    headers = {"User-Agent": UA, "Referer": REFERER,
               "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"}
    try:
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(url, headers=headers, impersonate="chrome124", timeout=60)
        if resp.status_code == 200 and resp.content:
            dest.write_bytes(resp.content)
            return True
    except Exception:  
        pass
    try:
        import requests
        resp = requests.get(url, headers=headers, timeout=60, stream=True)
        if resp.status_code == 200:
            with dest.open("wb") as fh:
                for chunk in resp.iter_content(65536):
                    fh.write(chunk)
            return dest.stat().st_size > 0
    except Exception as err:  
        log.warning("下载失败 %s：%s", url[:70], str(err)[:80])
    return False


_USABLE_FFMPEG: str | None = None

FFMPEG_SUFFIX = ".exe" if os.name == "nt" else ""


def _ffmpeg_candidates() -> list[str]:





    found: list[str] = []
    exe = shutil.which("ffmpeg")
    if exe:
        found.append(exe)
    for path in (
            Path("/usr/local/bin/ffmpeg"), Path("/usr/bin/ffmpeg"), Path("/opt/homebrew/bin/ffmpeg"),
            
            Path.home() / ".skill-runtime/binaries/node/workspace/node_modules"
                          / "ffmpeg-static" / f"ffmpeg{FFMPEG_SUFFIX}",
            
            SKILL_DIR / ".runtime" / "bin" / f"ffmpeg{FFMPEG_SUFFIX}",
    ):
        if path.exists():
            found.append(str(path))
    return found


def _can_decode(exe: str) -> bool:
    try:
        proc = subprocess.run([exe, "-hide_banner", "-decoders"],
                              capture_output=True, text=True, timeout=60)
        return bool(re.search(r"^\s*V[\.\w]{5}\s+h264\b", proc.stdout or "", re.M))
    except Exception:  
        return False


def find_ffmpeg() -> str:

    global _USABLE_FFMPEG
    if _USABLE_FFMPEG is not None:
        return _USABLE_FFMPEG
    _USABLE_FFMPEG = ""
    for candidate in _ffmpeg_candidates():
        if _can_decode(candidate):
            _USABLE_FFMPEG = candidate
            break
    return _USABLE_FFMPEG


def ffmpeg_available() -> bool:
    return bool(find_ffmpeg())


def _run_ffmpeg(args: list[str]) -> bool:
    exe = find_ffmpeg()
    if not exe:
        return False
    try:
        proc = subprocess.run([exe, "-y", "-loglevel", "error", *args],
                              capture_output=True, timeout=300)
        return proc.returncode == 0
    except Exception as err:  
        log.warning("ffmpeg 执行失败：%s", str(err)[:120])
        return False


def probe_duration(path: Path) -> float:


    if not path.exists():
        return 0.0
    if shutil.which("ffprobe"):
        try:
            proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                                  capture_output=True, text=True, timeout=60)
            return float((proc.stdout or "0").strip())
        except Exception:  
            pass
    exe = find_ffmpeg()
    if not exe:
        return 0.0
    try:
        proc = subprocess.run([exe, "-hide_banner", "-i", str(path)],
                              capture_output=True, text=True, timeout=60)
        match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", proc.stderr or "")
        if match:
            return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
    except Exception:  
        pass
    return 0.0


_FFMPEG_FILTERS: set | None = None


def ffmpeg_filters() -> set:

    global _FFMPEG_FILTERS
    if _FFMPEG_FILTERS is not None:
        return _FFMPEG_FILTERS
    exe = find_ffmpeg()
    if not exe:
        _FFMPEG_FILTERS = set()
        return _FFMPEG_FILTERS
    try:
        proc = subprocess.run([exe, "-hide_banner", "-filters"],
                              capture_output=True, text=True, timeout=60)
        _FFMPEG_FILTERS = set(re.findall(r"^\s*[.A-Z]*\s+(\w+)\s+\S+->\S+", proc.stdout or "", re.M))
    except Exception:  
        _FFMPEG_FILTERS = set()
    return _FFMPEG_FILTERS


def _make_sheet(frames: list[Path], dest: Path, cols: int = 4, cell_w: int = 300) -> bool:

    try:
        from PIL import Image
        thumbs = []
        for f in frames[:20]:
            with Image.open(f) as im:
                im = im.convert("RGB")
                w, h = im.size
                im = im.resize((cell_w, max(1, int(h * cell_w / w))))
                thumbs.append(im)
        if not thumbs:
            return False
        rows = (len(thumbs) + cols - 1) // cols
        cell_h = max(t.height for t in thumbs)
        sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (18, 18, 22))
        for i, t in enumerate(thumbs):
            sheet.paste(t, ((i % cols) * cell_w, (i // cols) * cell_h))
        dest.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(dest, quality=82)
        return True
    except Exception:  
        pass
    if "tile" in ffmpeg_filters():
        return _run_ffmpeg(["-i", str(frames[0].parent.parent / "video.mp4"),
                            "-vf", f"fps=1/2,scale={cell_w}:-1,tile={cols}x5",
                            "-frames:v", "1", str(dest)])
    return False


def extract_frames(video: Path, out_dir: Path, scene_threshold: float = 0.35) -> list[str]:





    if not ffmpeg_available():
        log.warning("未检测到可用的 ffmpeg（playwright 内置版无解码器，不算），"
                    "跳过抽帧；封面与视频仍会正常下载")
        return []
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for stale in frames_dir.glob("*.jpg"):
        stale.unlink()

    frames: list[str] = []
    if "select" in ffmpeg_filters():
        _run_ffmpeg(["-i", str(video),
                     "-vf", f"select='gt(scene,{scene_threshold})',scale=480:-1",
                     "-vsync", "vfr", "-frames:v", "24", str(frames_dir / "%02d.jpg")])
        frames = sorted(p.name for p in frames_dir.glob("*.jpg"))

    if len(frames) < 3:
        for stale in frames_dir.glob("*.jpg"):
            stale.unlink()
        
        duration = probe_duration(video) or 40.0
        rate = max(0.2, min(2.0, 20.0 / max(duration, 1.0)))
        _run_ffmpeg(["-i", str(video), "-vf", "scale=480:-1", "-r", f"{rate:.3f}",
                     "-frames:v", "24", str(frames_dir / "%02d.jpg")])
        frames = sorted(p.name for p in frames_dir.glob("*.jpg"))

    if frames:
        _make_sheet([frames_dir / f for f in frames], out_dir / "sheet.jpg")
    return frames


def download_media(dataset: dict, media_dir: Path, top_k: int = 8,
                   note_ids: Optional[list[str]] = None) -> dict:

    media_dir = Path(media_dir)
    media_dir.mkdir(parents=True, exist_ok=True)
    notes = dataset.get("notes", [])
    if note_ids:
        picked = [n for n in notes if n.get("note_id") in note_ids]
    else:
        picked = sorted(notes, key=lambda n: n.get("liked") or 0, reverse=True)[:top_k]

    stats = {"notes": 0, "covers": 0, "videos": 0, "frames": 0, "items": []}
    for note in picked:
        nid = note.get("note_id")
        if not nid:
            continue
        folder = media_dir / nid
        item = {"note_id": nid, "title": note.get("title") or note.get("desc", "")[:30],
                "type": note.get("type"), "liked": note.get("liked", 0)}

        cover = note.get("cover") or (note.get("images") or [{}])[0].get("url")
        if _save(cover, folder / "cover.jpg"):
            
            item["cover"] = (folder / "cover.jpg").resolve().as_posix()
            stats["covers"] += 1

        if len(note.get("images") or []) > 1:
            for i, img in enumerate(note["images"][:9], 1):
                if _save(img.get("url", ""), folder / "images" / f"{i:02d}.jpg"):
                    item.setdefault("images", []).append(f"images/{i:02d}.jpg")

        if note.get("type") == "video" and note.get("video_url"):
            video_path = folder / "video.mp4"
            if _save(note["video_url"], video_path) and video_path.stat().st_size > 1024:
                item["video"] = video_path.resolve().as_posix()
                item["duration_sec"] = round(note.get("duration_ms", 0) / 1000, 1) or \
                    round(probe_duration(video_path), 1)
                stats["videos"] += 1
                frames = extract_frames(video_path, folder)
                item["frames"] = frames
                item["sheet"] = (folder / "sheet.jpg").resolve().as_posix() if frames else ""
                stats["frames"] += len(frames)

        stats["items"].append(item)
        stats["notes"] += 1
        log.info("素材 %s：封面%s 视频%s 关键帧%s", nid[:12],
                 "√" if item.get("cover") else "×",
                 "√" if item.get("video") else "×", len(item.get("frames", [])))

    write_json(media_dir / "media_index.json", stats)
    return stats


if __name__ == "__main__":
    import argparse
    from xhs_common import read_json

    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="dataset.json 路径")
    parser.add_argument("--out", default="", help="素材目录，默认 dataset 同级 media/")
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--note-id", action="append", dest="note_ids")
    args = parser.parse_args()

    data = read_json(Path(args.dataset))
    out = Path(args.out) if args.out else Path(args.dataset).parent / "media"
    result = download_media(data, out, args.top, args.note_ids)
    print(f"素材就绪：{result['notes']} 条笔记 / {result['covers']} 封面 / "
          f"{result['videos']} 视频 / {result['frames']} 关键帧 -> {out}")
