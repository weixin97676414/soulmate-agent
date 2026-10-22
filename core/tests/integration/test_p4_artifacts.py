






from __future__ import annotations

import pytest

from .conftest import FakeLLM, install_fake_model, make_client, read_sse, tool_call


@pytest.fixture
async def http(base_url):
    async with make_client(base_url) as client:
        yield client


async def put_artifact(runtime, name: str, content: str):

    path = runtime.paths.artifacts_dir / name
    path.write_text(content, encoding="utf-8")
    return await runtime.workspace.register_artifact(path, note="测试产物")





async def test_preview_svg_artifact(runtime, http):
    record = await put_artifact(
        runtime, "chart.svg", '<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>'
    )

    body = (await http.get(f"/v1/files/{record.id}/preview")).json()
    assert body["kind"] == "svg"
    assert "<circle" in body["content"]
    assert body["download_url"].endswith(record.id + "?kind=artifact")


async def test_chinese_artifact_name_preview_and_download(runtime, http):









    svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="4" height="4"/></svg>'
    record = await put_artifact(runtime, "业务架构图.svg", svg)
    assert record.id == "业务架构图.svg"

    preview = await http.get(f"/v1/files/{record.id}/preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["kind"] == "svg"

    download = await http.get(f"/v1/files/{record.id}?kind=artifact")
    assert download.status_code == 200, download.text
    assert "<rect" in download.text

    
    
    assert await runtime.workspace.delete(record.id, kind="artifact") is True


async def test_preview_markdown_artifact(runtime, http):
    record = await put_artifact(runtime, "report.md", "# 周报\n\n完成了 P4。")

    body = (await http.get(f"/v1/files/{record.id}/preview")).json()
    assert body["kind"] == "markdown"
    assert "P4" in body["content"]


async def test_preview_csv_artifact_as_table(runtime, http):
    record = await put_artifact(runtime, "sales.csv", "月份,金额\n1月,100\n2月,200")

    body = (await http.get(f"/v1/files/{record.id}/preview")).json()
    assert body["kind"] == "table"
    assert body["sheets"][0]["columns"] == ["月份", "金额"]
    assert len(body["sheets"][0]["rows"]) == 2


async def test_preview_missing_file_is_404(runtime, http):
    assert (await http.get("/v1/files/nope/preview")).status_code == 404


async def test_preview_rejects_bad_kind(runtime, http):
    assert (await http.get("/v1/files/whatever/preview?kind=bogus")).status_code == 422


async def test_uploaded_file_can_also_be_previewed(runtime, http):

    response = await http.post(
        "/v1/files/upload",
        files={"file": ("data.csv", b"a,b\n1,2", "text/csv")},
    )
    assert response.status_code == 200, response.text
    file_id = response.json()["id"]

    body = (await http.get(f"/v1/files/{file_id}/preview?kind=upload")).json()
    assert body["kind"] == "table"





async def test_artifact_appears_in_list(runtime, http):
    await put_artifact(runtime, "out.md", "内容")
    body = (await http.get("/v1/files?kind=artifact")).json()
    assert [item["original_name"] for item in body["files"]] == ["out.md"]
    assert body["stats"]["artifacts"] >= 1





async def test_trace_shape_is_consistent(runtime, http):







    llm = FakeLLM(["你好", "再见"])
    install_fake_model(runtime, llm)

    events = await read_sse(http, {"message": "打个招呼", "model_id": "fake"})
    trace = next(data for name, data in events if name == "trace")

    spans = trace["spans"]
    assert spans
    
    roots = [span for span in spans if not span.get("parent_id")]
    assert sum(span["duration_ms"] for span in roots) <= trace["total_duration_ms"] + 1
    assert trace["total_duration_ms"] > 0


async def test_trace_spans_carry_timeline_offsets(runtime, http):

    llm = FakeLLM(
        [
            _tool_response("calc", {"expression": "1+1"}),
            "结果是 2。",
        ]
    )
    install_fake_model(runtime, llm)

    events = await read_sse(http, {"message": "算一下", "model_id": "fake"})
    trace = next(data for name, data in events if name == "trace")

    for span in trace["spans"]:
        assert "start_ms" in span and "end_ms" in span
        assert span["end_ms"] >= span["start_ms"]

    starts = [span["start_ms"] for span in trace["spans"]]
    assert min(starts) >= 0
    
    assert max(span["end_ms"] for span in trace["spans"]) <= trace["total_duration_ms"] + 60


async def test_trace_marks_nested_spans(runtime, http):

    llm = FakeLLM(
        [
            _tool_response("calc", {"expression": "2*3"}),
            "等于 6。",
        ]
    )
    install_fake_model(runtime, llm)

    events = await read_sse(http, {"message": "算一下", "model_id": "fake"})
    trace = next(data for name, data in events if name == "trace")

    by_id = {span["span_id"]: span for span in trace["spans"]}
    skill_spans = [span for span in trace["spans"] if span["name"].startswith("skill:")]
    assert skill_spans, "工具执行必须被记录成 span"

    skill = skill_spans[0]
    assert skill["parent_id"] in by_id
    assert by_id[skill["parent_id"]]["name"].startswith("step:")


async def test_trace_counts_tokens(runtime, http):
    llm = FakeLLM(["你好"])
    install_fake_model(runtime, llm)

    events = await read_sse(http, {"message": "你好", "model_id": "fake"})
    trace = next(data for name, data in events if name == "trace")
    assert trace["total_tokens"] == trace["prompt_tokens"] + trace["completion_tokens"]
    assert trace["total_tokens"] > 0


def _tool_response(name: str, arguments: dict):
    from my_agent.llm.base import LLMResponse

    return LLMResponse(
        tool_calls=[tool_call(name, arguments, call_id=f"call_{name}")],
        finish_reason="tool_calls",
    )
