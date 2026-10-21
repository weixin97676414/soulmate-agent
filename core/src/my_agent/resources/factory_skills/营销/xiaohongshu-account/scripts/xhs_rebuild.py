


















from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import xhs_common as common  
from xhs_common import read_json, write_json  

log = common.log


def _load_payloads(api_dir: Path, prefix: str) -> list[dict]:
    files = sorted(api_dir.glob(f"{prefix}_*.json"))
    out = []
    for f in files:
        data = read_json(f)
        if isinstance(data, dict):
            out.append(data)
    return out


def collect_notes(api_dir: Path) -> list[dict]:

    seen: set[str] = set()
    notes: list[dict] = []
    for payload in _load_payloads(api_dir, "user_posted"):
        for n in ((payload.get("data") or {}).get("notes") or []):
            card = n.get("note_card") or n.get("noteCard") or {}
            nid = card.get("note_id") or card.get("noteId") or n.get("note_id") or n.get("noteId")
            if nid and nid not in seen:
                seen.add(nid)
                notes.append(n)
    return notes


def collect_profile(api_dir: Path, fallback: dict | None = None) -> dict:
    for payload in _load_payloads(api_dir, "user_info"):
        user = (payload.get("data") or {}).get("user")
        if user:
            return user
    return fallback or {}


def main() -> int:
    ap = argparse.ArgumentParser(description="从 raw/api 原始响应重建 dataset.json")
    ap.add_argument("--out", required=True, help="任务输出目录（含 raw/api/）")
    ap.add_argument("--media", action="store_true", help="重建后下载封面与关键帧素材")
    ap.add_argument("--media-top", type=int, default=10, help="下载素材的笔记数（按点赞排序）")
    args = ap.parse_args()

    out_dir = Path(args.out)
    api_dir = out_dir / "raw" / "api"
    if not api_dir.is_dir():
        log.error("找不到 %s，无法离线重建（该目录存放带 note_id 的接口原始响应）", api_dir)
        return 1

    from xhs_crawl import normalize_note, normalize_profile
    from xhs_resolve import Target

    old = read_json(out_dir / "dataset.json") or {}
    old_meta = old.get("meta") or {}
    t = old_meta.get("target") or {}
    target = Target(uid=t.get("uid", ""), nickname=t.get("nickname", ""),
                    xsec_token=t.get("xsec_token", ""), profile_url=t.get("profile_url", ""),
                    raw=t.get("raw", ""), resolved_by=t.get("resolved_by", ""))

    raw_notes = collect_notes(api_dir)
    if not raw_notes:
        log.error("raw/api 里没有带 note_id 的笔记，重建失败")
        return 1

    profile = normalize_profile(collect_profile(api_dir, old.get("profile")), target)
    notes = [normalize_note(n, profile) for n in raw_notes]
    notes = [n for n in notes if n.get("note_id")]

    write_json(out_dir / "raw" / "profile.json", profile)
    write_json(out_dir / "raw" / "notes.json", notes)

    
    valid_ids = {n["note_id"] for n in notes}
    detail_files = [p for p in (out_dir / "raw" / "notes").glob("*.json") if p.stem in valid_ids]
    has_comments = any((out_dir / "raw" / "comments" / f"{p.stem}.json").exists()
                       for p in detail_files)

    dataset = {
        "meta": {
            "target": target.to_dict(),
            "tier": f"{old_meta.get('tier', 'unknown')}+rebuilt",
            "crawled_at": old_meta.get("crawled_at", ""),
            "rebuilt_at": common.time.strftime("%Y-%m-%d %H:%M:%S"),
            "rebuilt": True,
            "rebuilt_from": str(api_dir),
            "note_limit": 0,
            "full_crawl": True,
            "detail_top": len(detail_files),
            "detail_all": False,
            "has_comments": has_comments,
            "comments_limit": old_meta.get("comments_limit", 100),
            "skill": "xhs-account-deconstruct",
        },
        "profile": profile,
        "notes": notes,
    }

    
    from xhs_crawl import _merge_details
    _merge_details(out_dir, dataset)
    notes = dataset["notes"]

    if args.media:
        try:
            from xhs_media import download_media
            dataset["meta"]["media"] = download_media(
                dataset, out_dir / "media", args.media_top)
        except Exception as err:  
            log.warning("素材下载失败（不影响文本分析）：%s", err)
            dataset["meta"]["media"] = {"error": str(err)[:200]}

    dataset["notes"].sort(key=lambda n: n.get("timestamp") or 0, reverse=True)
    write_json(out_dir / "dataset.json", dataset)

    log.info("重建完成：%s 条笔记（来自 %s 个接口响应）", len(notes),
             len(list(api_dir.glob("user_posted_*.json"))))
    log.info("账号：%s（小红书号 %s）", profile.get("nickname"), profile.get("red_id"))
    if not detail_files:
        log.warning("没有可用的详情文件：本次仅含列表指标（点赞/形式/时间），"
                    "缺少收藏、评论、正文与标签")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
