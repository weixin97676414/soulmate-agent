#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "xiaohongshu_links.py"
)
SPEC = importlib.util.spec_from_file_location("xiaohongshu_links", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class XiaohongshuLinksTests(unittest.TestCase):
    def run_cli(
        self,
        payload: object,
        *,
        purpose: str,
        limit: int = 5,
        expect: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--purpose",
                purpose,
                "--limit",
                str(limit),
            ],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result

    def test_current_search_paths_and_trailing_slash(self):
        for path in ("explore", "note", "search_result", "discovery/item"):
            for suffix in ("", "/"):
                with self.subTest(path=path, suffix=suffix):
                    result = self.run_cli([{"url": f"https://www.xiaohongshu.com/{path}/abc123{suffix}?xsec_token=token"}], purpose="response")
                    self.assertIn("/discovery/item/abc123?source=webshare", result.stdout)

    def test_user_can_request_twenty_results(self):
        payload = [{"feed_id": f"item{i}"} for i in range(21)]
        result = self.run_cli(payload, purpose="persistence", limit=20)
        self.assertEqual(len(json.loads(result.stdout)["results"]), 20)

    def test_ambiguous_ids_and_duplicate_blank_tokens_rejected(self):
        payloads = [
            {"url": "https://www.xiaohongshu.com/explore/abc123?xsec_token=&xsec_token=token"},
            {"url": "https://www.xiaohongshu.com/search_result/abc123?xsec_token=token", "note_id": "different"},
            {"note_id": "abc123", "feed_id": "different"},
        ]
        for record in payloads:
            self.assertEqual(self.run_cli([record], purpose="response", expect=2).stdout, "")

    def test_special_token_roundtrip(self):
        from urllib.parse import parse_qs, urlsplit
        token = "a+b/c= &中文"
        result = self.run_cli([{"note_id": "abc123", "xsec_token": token}], purpose="response")
        url = json.loads(result.stdout)["results"][0]["share_url"]
        self.assertEqual(parse_qs(urlsplit(url).query)["xsec_token"], [token])

    def test_response_contains_only_openable_share_url(self) -> None:
        result = self.run_cli(
            [
                {
                    "rank": 1,
                    "title": "课程结果",
                    "published_at": "2025-01-15",
                    "url": (
                        "https://www.xiaohongshu.com/search_result/abc123"
                        "?xsec_source=pc_search&xsec_token=token%3D"
                    ),
                }
            ],
            purpose="response",
        )
        output = json.loads(result.stdout)
        record = output["results"][0]
        self.assertNotIn("canonical_url", record)
        self.assertNotIn("/search_result/", result.stdout)
        self.assertEqual(
            record["share_url"],
            (
                "https://www.xiaohongshu.com/discovery/item/abc123"
                "?source=webshare&xhsshare=pc_web"
                "&xsec_token=token=&xsec_source=pc_share"
            ),
        )
        self.assertEqual(
            set(record),
            {"title", "published_at", "share_url"},
        )

    def test_limit_five_is_accepted_and_bounds_output(self) -> None:
        result = self.run_cli(
            [
                {
                    "feed_id": f"item{index}",
                    "xsec_token": "token",
                    "title": f"Result {index}",
                }
                for index in range(6)
            ],
            purpose="response",
            limit=5,
        )
        self.assertEqual(len(json.loads(result.stdout)["results"]), 5)

    def test_limit_101_is_rejected_without_converted_records(self) -> None:
        result = self.run_cli(
            [{"feed_id": "item1", "xsec_token": "token"}],
            purpose="response",
            limit=101,
            expect=2,
        )
        self.assertEqual(result.stdout, "")
        self.assertNotIn('"results"', result.stderr)

    def test_library_rejects_limit_outside_contract(self) -> None:
        for limit in (0, 101, True):
            with self.subTest(limit=limit):
                with self.assertRaises(MODULE.XiaohongshuLinkError):
                    MODULE.convert([], purpose="response", limit=limit)

    def test_library_rejects_invalid_purpose_before_empty_records(self) -> None:
        for purpose in ("invalid-purpose", None, 1, True):
            with self.subTest(purpose=purpose):
                with self.assertRaisesRegex(
                    MODULE.XiaohongshuLinkError,
                    "purpose must be response or persistence",
                ):
                    MODULE.convert([], purpose=purpose, limit=5)

    def test_persistence_strips_token_and_tracking_query(self) -> None:
        result = self.run_cli(
            [
                {
                    "url": (
                        "https://www.xiaohongshu.com/search_result/abc123"
                        "?xsec_source=pc_search&xsec_token=ephemeral"
                    )
                }
            ],
            purpose="persistence",
        )
        output = json.loads(result.stdout)
        record = output["results"][0]
        self.assertEqual(
            record["canonical_url"],
            "https://www.xiaohongshu.com/discovery/item/abc123",
        )
        self.assertNotIn("share_url", record)
        self.assertNotIn("xsec_", result.stdout)

    def test_mapped_backend_record_uses_same_contract(self) -> None:
        result = self.run_cli(
            [
                {
                    "feed_id": "mapped456",
                    "xsec_token": "mapped-token=",
                    "title": "Mapped result",
                }
            ],
            purpose="response",
        )
        output = json.loads(result.stdout)
        self.assertIn(
            "/discovery/item/mapped456?source=webshare",
            output["results"][0]["share_url"],
        )

    def test_missing_token_does_not_fabricate_share_url(self) -> None:
        result = self.run_cli(
            [
                {
                    "url": (
                        "https://www.xiaohongshu.com/search_result/noToken"
                    )
                }
            ],
            purpose="response",
        )
        output = json.loads(result.stdout)
        self.assertEqual(output["results"][0]["share_url"], "")
        self.assertEqual(
            set(output["results"][0]),
            {"title", "published_at", "share_url"},
        )

    def test_title_cannot_inject_a_second_url(self) -> None:
        result = self.run_cli(
            [
                {
                    "title": (
                        "课程 https://www.xiaohongshu.com/search_result/leak"
                    ),
                    "url": (
                        "https://www.xiaohongshu.com/search_result/safe123"
                        "?xsec_token=token"
                    ),
                }
            ],
            purpose="response",
        )
        output = json.loads(result.stdout)
        self.assertEqual(
            output["results"][0]["title"],
            "课程 [链接已省略]",
        )
        self.assertNotIn("/search_result/leak", result.stdout)

    def test_untrusted_rank_and_case_variant_urls_are_removed(self) -> None:
        forbidden_url = "HTTPS://evil.example/second-link"
        payload = [
            {
                "rank": {
                    "url": "https://evil.example/rank-link",
                    "payload": ["UNTRUSTED_RANK_PAYLOAD"],
                },
                "title": f"课程 {forbidden_url}",
                "published_at": "2025-01-15 HTTP://evil.example/date-link",
                "url": (
                    "https://www.xiaohongshu.com/search_result/safe123"
                    "?xsec_token=token"
                ),
            }
        ]
        for purpose in ("response", "persistence"):
            with self.subTest(purpose=purpose):
                result = self.run_cli(payload, purpose=purpose)
                record = json.loads(result.stdout)["results"][0]
                self.assertNotIn("rank", record)
                self.assertEqual(record["title"], "课程 [链接已省略]")
                self.assertEqual(
                    record["published_at"],
                    "2025-01-15 [链接已省略]",
                )
                self.assertNotIn("evil.example", result.stdout.lower())
                self.assertNotIn("UNTRUSTED_RANK_PAYLOAD", result.stdout)

    def test_consumed_fields_reject_non_string_json_values(self) -> None:
        invalid_values = ({"nested": "payload"}, ["nested"], True, None)
        fields = (
            "url",
            "note_id",
            "feed_id",
            "xsec_token",
            "title",
            "published_at",
        )
        for purpose in ("response", "persistence"):
            for field in fields:
                for invalid in invalid_values:
                    with self.subTest(
                        purpose=purpose,
                        field=field,
                        invalid=invalid,
                    ):
                        record = {
                            "url": (
                                "https://www.xiaohongshu.com/search_result/safe123"
                                "?xsec_token=token"
                            ),
                            "title": "Safe title",
                            "published_at": "2025-01-15",
                        }
                        record[field] = invalid
                        if field == "url":
                            record["feed_id"] = "safe123"
                        result = self.run_cli(
                            [record],
                            purpose=purpose,
                            expect=2,
                        )
                        self.assertEqual(result.stdout, "")
                        self.assertIn(f"{field} must be a string", result.stderr)
                        self.assertNotIn("nested", result.stderr)

    def test_persistence_record_has_exact_declared_fields(self) -> None:
        result = self.run_cli(
            [
                {
                    "feed_id": "mapped456",
                    "xsec_token": "mapped-token",
                    "title": "Mapped result",
                    "published_at": "2025-01-15",
                }
            ],
            purpose="persistence",
        )
        self.assertEqual(
            set(json.loads(result.stdout)["results"][0]),
            {"title", "published_at", "canonical_url"},
        )

    def test_only_canonical_www_host_is_accepted(self) -> None:
        accepted = self.run_cli(
            [
                {
                    "url": (
                        "https://www.xiaohongshu.com/search_result/accepted123"
                        "?xsec_token=token"
                    )
                }
            ],
            purpose="response",
        )
        self.assertIn("/discovery/item/accepted123", accepted.stdout)

        for host in (
            "xiaohongshu.com",
            "m.xiaohongshu.com",
            "www.xiaohongshu.com.",
            "www.xiaohongshu.com:8443",
            "www.xiaohongshu.com.evil.example",
        ):
            with self.subTest(host=host):
                rejected = self.run_cli(
                    [
                        {
                            "url": (
                                f"https://{host}/search_result/rejected123"
                                "?xsec_token=token"
                            )
                        }
                    ],
                    purpose="response",
                    expect=2,
                )
                self.assertEqual(rejected.stdout, "")
                self.assertIn("unexpected Xiaohongshu result URL", rejected.stderr)

    def test_wrong_host_is_rejected_without_echoing_payload(self) -> None:
        result = self.run_cli(
            [{"url": "https://example.com/search_result/bad?xsec_token=secret"}],
            purpose="response",
            expect=2,
        )
        self.assertIn("REJECTED", result.stderr)
        self.assertNotIn("secret", result.stderr)

    def test_http_source_is_rejected(self) -> None:
        result = self.run_cli(
            [
                {
                    "url": (
                        "http://www.xiaohongshu.com/search_result/bad"
                        "?xsec_token=token"
                    )
                }
            ],
            purpose="response",
            expect=2,
        )
        self.assertIn("REJECTED", result.stderr)


if __name__ == "__main__":
    unittest.main()
