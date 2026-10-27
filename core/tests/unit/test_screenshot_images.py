





from __future__ import annotations

from my_agent.agent.engine import AgentConfig
from my_agent.llm.base import ImagePart
from my_agent.skill.base import SkillContext


def test_emit_image_without_outbox_is_silent() -> None:

    ctx = SkillContext()
    ctx.emit_image("data:image/png;base64,AAAA")


def test_emit_image_appends_to_outbox() -> None:
    ctx = SkillContext()
    bucket: list[ImagePart] = []
    ctx.set_image_outbox(bucket)

    ctx.emit_image("data:image/png;base64,AAAA")

    ctx.set_image_outbox(None)
    assert len(bucket) == 1
    assert bucket[0].data_url == "data:image/png;base64,AAAA"
    assert bucket[0].mime == "image/png"


def test_emit_empty_image_is_ignored() -> None:
    ctx = SkillContext()
    bucket: list[ImagePart] = []
    ctx.set_image_outbox(bucket)
    ctx.emit_image("")
    ctx.set_image_outbox(None)
    assert bucket == []


def test_agent_config_defaults_to_no_vision() -> None:

    assert AgentConfig().supports_vision is False


def test_image_part_does_not_leak_base64_in_repr() -> None:

    part = ImagePart(data_url="data:image/png;base64,VERYLONGBASE64")
    assert "VERYLONGBASE64" not in repr(part)
