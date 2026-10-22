#!/usr/bin/env python3
















import asyncio
import os
import re
import sys
import json
import requests
from pathlib import Path
from urllib.parse import unquote


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
    transcribe,
    write_cleaned_md,
)


check_dependencies(require_douyin=False)



_playwright_available = False
_async_playwright = None

try:
    from playwright.async_api import async_playwright   
    _playwright_available = True
    _async_playwright = async_playwright
except ImportError:
    print("[Info] playwright 未安装，抖音视频将使用 API 方案获取（无需浏览器）")




OUTPUT_DIR = "."




async def _try_capture_once(short_url: str, wait_seconds: int) -> tuple[str | None, str]:









    async with _async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        await page.goto(short_url, wait_until="domcontentloaded", timeout=30000)
        print(f"[Step 1] 等待 JS 渲染 ({wait_seconds}秒)...")
        await asyncio.sleep(wait_seconds)

        
        selectors = [
            'video[src*="douyin"]',
            'video[src*="douyinvod"]',
            'video[src*="aweme"]',
            'video',
            'xgplayer-container video',
        ]

        video_src = None
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    src = await el.get_attribute("src")
                    if src and ".mp4" in src and ("douyin" in src or "douyinvod" in src or "aweme" in src):
                        video_src = src
                        print(f"[Step 1] 通过选择器捕获: {sel}")
                        break
            except Exception:
                pass

        
        if not video_src:
            video_src = await page.evaluate("""
                () => {
                    const videos = document.querySelectorAll('video');
                    for (const v of videos) {
                        if (v.src && v.src.includes('.mp4') && (v.src.includes('douyin') || v.src.includes('douyinvod') || v.src.includes('aweme')))
                            return v.src;
                        const sources = v.querySelectorAll('source');
                        for (const s of sources) { if (s.src) return s.src; }
                    }
                    return null;
                }
            """)
            if video_src:
                print("[Step 1] 通过 page.evaluate 捕获")

        final_url = page.url
        print(f"[Step 1] 解析后页面: {final_url}")
        await browser.close()

    return video_src, final_url


async def capture_video_url(short_url: str) -> tuple[str | None, str]:










    if not _playwright_available:
        print("[Step 1] playwright 不可用，跳过浏览器捕获")
        return None, ""

    print(f"[Step 1] 正在打开: {short_url}")

    
    video_src, final_url = await _try_capture_once(short_url, 8)

    if video_src:
        print(f"[Step 1] 视频 URL 已获取 ({len(video_src)} 字符)")
        return video_src, final_url

    
    print("[Step 1] 首次捕获失败，增加等待时间重试...")
    video_src, final_url = await _try_capture_once(short_url, 13)

    if video_src:
        print(f"[Step 1] 重试成功！视频 URL 已获取 ({len(video_src)} 字符)")
        return video_src, final_url

    print("[Step 1] Playwright 捕获失败（2次尝试均未找到视频 URL）")
    return None, final_url




def download_video(url: str, output_path: str, referer: str = "https://www.douyin.com/") -> str:

    print(f"[Step 2] 下载中: {output_path}")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": referer,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    resp = requests.get(url, headers=headers, stream=True, timeout=120, allow_redirects=True)
    print(f"[Step 2] HTTP {resp.status_code} | Content-Type: {resp.headers.get('Content-Type')}")

    if not resp.ok:
        raise RuntimeError(f"下载失败: HTTP {resp.status_code}")

    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    print(f"  {downloaded/1024/1024:.1f} MB / {total/1024/1024:.1f} MB", end="\r")

    size_mb = downloaded / 1024 / 1024
    print(f"\n[Step 2] 下载完成: {size_mb:.1f} MB")
    return output_path





def _fix_douyin_text(text: str) -> str:









    if not text:
        return text

    
    
    suspicious_chars = sum(1 for c in text if 0x80 <= ord(c) <= 0xFF and ord(c) > 0x9F)
    total_non_ascii = sum(1 for c in text if ord(c) > 127)

    
    if suspicious_chars > 0 and total_non_ascii > 0 and suspicious_chars / total_non_ascii > 0.3:
        try:
            fixed = text.encode("latin1").decode("utf-8")
            
            chinese_chars = sum(1 for c in fixed if 0x4E00 <= ord(c) <= 0x9FFF)
            if chinese_chars > 0:
                return fixed
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass  

    return text


def _extract_video_id(url: str) -> str | None:









    
    match = re.search(r'/(?:video|note|modal|share/video)/(\d+)', url)
    if match:
        return match.group(1)

    
    match = re.search(r'modal_id=(\d+)', url)
    if match:
        return match.group(1)

    return None


def fetch_video_url_via_api(short_url: str) -> tuple[str | None, str, dict | None]:










    print("[Step 1-备用] 尝试通过 Douyin API 获取视频 URL...")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
    }

    
    try:
        resp = requests.get(short_url, headers=headers, timeout=15, allow_redirects=True)
        resolved_url = resp.url
        print(f"[Step 1-备用] 解析后页面: {resolved_url}")
    except Exception as e:
        print(f"[Step 1-备用] 访问短链接失败: {e}")
        return None, "", None

    video_id = _extract_video_id(resolved_url)
    if not video_id:
        print("[Step 1-备用] 无法从 URL 中提取视频 ID")
        return None, resolved_url, None

    print(f"[Step 1-备用] 视频 ID: {video_id}")

    
    api_url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}&aid=6383"
    try:
        api_resp = requests.get(api_url, headers={
            "User-Agent": headers["User-Agent"],
            "Referer": "https://www.douyin.com/",
            "Accept": "application/json",
        }, timeout=15)
        print(f"[Step 1-备用] API HTTP {api_resp.status_code}")

        if not api_resp.ok:
            print(f"[Step 1-备用] API 请求失败")
            return None, resolved_url, None

        data = api_resp.json()
        detail = data.get("aweme_detail")
        if not detail:
            print(f"[Step 1-备用] API 返回无 aweme_detail（status_code={data.get('status_code', 'N/A')}）")
            return None, resolved_url, None

        
        play_addr = detail.get("video", {}).get("play_addr", {})
        url_list = play_addr.get("url_list", [])
        if not url_list:
            print("[Step 1-备用] API 返回无视频 URL")
            return None, resolved_url, detail

        video_url = url_list[0]
        
        video_url = video_url.replace("~", "%7E")

        desc = _fix_douyin_text(detail.get("desc", ""))

        author = _fix_douyin_text(detail.get("author", {}).get("nickname", ""))

        print(f"[Step 1-备用] 视频 URL 已获取 ({len(video_url)} 字符)")
        print(f"[Step 1-备用] 描述: {desc[:80]}")
        print(f"[Step 1-备用] 作者: {author}")
        return video_url, resolved_url, detail

    except Exception as e:
        print(f"[Step 1-备用] API 调用失败: {e}")
        return None, resolved_url, None




async def main():
    args = sys.argv[1:]
    if not args:
        print("用法: python fetch_douyin_video.py <douyin_short_url> [--output DIR]")
        print("示例: python fetch_douyin_video.py https://v.douyin.com/xxxxx/")
        print("      python fetch_douyin_video.py https://v.douyin.com/xxxxx/ --output ./result")
        sys.exit(1)

    
    output_dir = OUTPUT_DIR

    if "--output" in args:
        idx = args.index("--output")
        if idx + 1 < len(args):
            output_dir = args.pop(idx + 1)
        args.pop(idx)

    if not args:
        print("[ERROR] 请提供抖音短链接")
        sys.exit(1)

    short_url = args[0]

    ts = make_timestamp()
    print(f"[Info] 时间戳: {ts}")
    print(f"[Info] 输出目录: {output_dir}")
    print("[Info] 流程: Step1 捕获URL -> Step2 下载视频 -> Step3 Whisper转录 -> Step4 整理输出")

    
    print("\n[Step 1/4] 正在捕获视频 URL...")
    video_url, resolved_url = await capture_video_url(short_url)

    if not video_url:
        print("[Step 1] Playwright 捕获失败，尝试 API 备用方案...")
        video_url, resolved_url, _detail = fetch_video_url_via_api(short_url)

    if not video_url:
        print("[ERROR] 未能捕获视频 URL（Playwright 和 API 均失败），请确认链接有效")
        print("  提示：某些视频需要登录后才能播放，可尝试使用完整视频页面 URL")
        sys.exit(1)

    
    print("\n[Step 2/4] 正在下载视频...")
    video_filename = f"douyin_video_{ts}.mp4"
    video_path = os.path.join(output_dir, video_filename)
    video_path = download_video(video_url, video_path, resolved_url or "https://www.douyin.com/")

    
    print("\n[Step 3/4] 正在转录（Whisper medium 模型，耗时取决于视频长度）...")
    result, txt_path, json_path = transcribe(video_path, output_dir, timestamp=ts)

    
    raw_text = result["text"].strip()
    print("\n[Step 4/4] 转录完成，请 agent 整理后调用 write_cleaned_md() 写入 MD")
    print(f"[Step 4/4] RAW_TRANSCRIPT_START\n{raw_text}\n[Step 4/4] RAW_TRANSCRIPT_END")

    print("\n[Done] 转录完毕")
    print(f"  视频:   {video_path}")
    print(f"  文本:   {txt_path}")
    print(f"  JSON:   {json_path}")
    print(f"  时间戳: {ts}")
    print(f"\n预览: {raw_text[:200]}...")

    
    return {
        "timestamp": ts,
        "video_path": video_path,
        "txt_path": txt_path,
        "json_path": json_path,
        "raw_text": raw_text,
        "source_url": short_url,
        "resolved_url": resolved_url,
        "segments": result["segments"],
    }


if __name__ == "__main__":
    asyncio.run(main())
