#!/usr/bin/env python3
"""Convert Xiaohongshu search results into purpose-separated safe links.

Read JSON from stdin and write converted JSON to stdout without network access.
Accept an OpenCLI-style ``url`` or ``note_id/feed_id`` plus ``xsec_token``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from urllib.parse import parse_qsl, quote, urlsplit


XHS_HOST = "www.xiaohongshu.com"
NOTE_PATH = re.compile(r"/(?:search_result|discovery/item|explore|note)/([A-Za-z0-9]+)/?")
URL_TEXT = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
MAX_TOKEN_LENGTH = 2048
MAX_RESULTS = 100
INPUT_STRING_FIELDS = (
    "url",
    "note_id",
    "feed_id",
    "xsec_token",
    "title",
    "published_at",
)


class XiaohongshuLinkError(RuntimeError):
    pass


def clean_text(value: str, limit: int) -> str:
    text = URL_TEXT.sub("[链接已省略]", value.strip())
    text = "".join(
        char for char in text if unicodedata.category(char) != "Cc"
    )
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def validate_note_id(value: str) -> str:
    note_id = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9]+", note_id):
        raise XiaohongshuLinkError("note_id/feed_id must be alphanumeric")
    return note_id


def validate_token(value: str) -> str:
    token = value.strip()
    if not token:
        return ""
    if len(token) > MAX_TOKEN_LENGTH or any(
        unicodedata.category(char) == "Cc" for char in token
    ):
        raise XiaohongshuLinkError("xsec_token is malformed")
    return token


def identity_from_url(value: str) -> tuple[str, str]:
    parts = urlsplit(value.strip())
    if parts.scheme != "https" or parts.hostname != XHS_HOST:
        raise XiaohongshuLinkError("unexpected Xiaohongshu result URL")
    try:
        port = parts.port
    except ValueError as error:
        raise XiaohongshuLinkError(
            "unexpected Xiaohongshu result URL authority"
        ) from error
    if parts.username or parts.password or port not in {None, 443}:
        raise XiaohongshuLinkError(
            "unexpected Xiaohongshu result URL authority"
        )
    match = NOTE_PATH.fullmatch(parts.path)
    if not match:
        raise XiaohongshuLinkError("unexpected Xiaohongshu result URL path")
    tokens = [
        item
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if key == "xsec_token"
    ]
    if len(tokens) > 1:
        raise XiaohongshuLinkError("multiple xsec_token values are not allowed")
    return validate_note_id(match.group(1)), validate_token(
        tokens[0] if tokens else ""
    )


def scalar_record(record: dict[str, object]) -> dict[str, str]:
    values: dict[str, str] = {}
    for field in INPUT_STRING_FIELDS:
        if field not in record:
            values[field] = ""
            continue
        value = record[field]
        if not isinstance(value, str):
            raise XiaohongshuLinkError(f"{field} must be a string")
        values[field] = value
    return values


def identity_from_record(record: dict[str, str]) -> tuple[str, str]:
    explicit_ids = [validate_note_id(record[field]) for field in ("note_id", "feed_id") if record[field].strip()]
    if len(set(explicit_ids)) > 1:
        raise XiaohongshuLinkError("note_id and feed_id disagree")
    if record["url"].strip():
        note_id, token = identity_from_url(record["url"])
        if explicit_ids and explicit_ids[0] != note_id:
            raise XiaohongshuLinkError("URL and record note IDs disagree")
        explicit_token = validate_token(record["xsec_token"])
        if explicit_token and token and explicit_token != token:
            raise XiaohongshuLinkError(
                "URL and record contain different xsec_token values"
            )
        return note_id, explicit_token or token
    note_id = validate_note_id(record["note_id"] or record["feed_id"])
    return note_id, validate_token(record["xsec_token"])


def canonical_url(note_id: str) -> str:
    return f"https://www.xiaohongshu.com/discovery/item/{note_id}"


def share_url(note_id: str, token: str) -> str:
    if not token:
        return ""
    encoded_token = quote(token, safe="-._~=")
    return (
        f"{canonical_url(note_id)}"
        "?source=webshare&xhsshare=pc_web"
        f"&xsec_token={encoded_token}&xsec_source=pc_share"
    )


def input_records(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, dict):
        payload = payload.get("results")
    if not isinstance(payload, list):
        raise XiaohongshuLinkError(
            "input must be a JSON list or an object with a results list"
        )
    if not all(isinstance(item, dict) for item in payload):
        raise XiaohongshuLinkError("each search result must be an object")
    return payload


def convert(
    payload: object,
    *,
    purpose: object,
    limit: int,
) -> dict[str, object]:
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_RESULTS
    ):
        raise XiaohongshuLinkError(
            f"limit must be an integer between 1 and {MAX_RESULTS}"
        )
    if not isinstance(purpose, str) or purpose not in {
        "response",
        "persistence",
    }:
        raise XiaohongshuLinkError(
            "purpose must be response or persistence"
        )
    results: list[dict[str, object]] = []
    for source in input_records(payload)[:limit]:
        scalar_source = scalar_record(source)
        note_id, token = identity_from_record(scalar_source)
        result: dict[str, object] = {
            "title": clean_text(scalar_source["title"], 120),
            "published_at": clean_text(scalar_source["published_at"], 40),
        }
        if purpose == "response":
            result["share_url"] = share_url(note_id, token)
        elif purpose == "persistence":
            result["canonical_url"] = canonical_url(note_id)
        results.append(result)

    policy = (
        "current response only; do not persist or reuse share_url"
        if purpose == "response"
        else "identity and dedup only; do not display canonical_url as a user link"
    )
    return {"purpose": purpose, "results": results, "policy": policy}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--purpose",
        required=True,
        choices=("response", "persistence"),
    )
    result.add_argument(
        "--limit",
        type=int,
        default=5,
        choices=range(1, MAX_RESULTS + 1),
    )
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        payload = json.load(sys.stdin)
        output = convert(payload, purpose=args.purpose, limit=args.limit)
    except (
        json.JSONDecodeError,
        XiaohongshuLinkError,
        TypeError,
        ValueError,
    ) as error:
        print(f"xiaohongshu link conversion: REJECTED\n{error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
