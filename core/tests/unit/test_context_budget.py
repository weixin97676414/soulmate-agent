













from __future__ import annotations

from types import SimpleNamespace

import pytest

from my_agent.config.schemas import AgentSettings
from my_agent.server.runtime import AppRuntime


FALLBACK_TOKENS = 32768


def budget(window: int | None, cap: int) -> int:







    def get(_model_id: str | None):
        if window is None:
            raise KeyError("模型不存在")
        return SimpleNamespace(token_limit=window)

    fake = SimpleNamespace(
        registry=SimpleNamespace(get=get),
        config=SimpleNamespace(
            settings=SimpleNamespace(agent=SimpleNamespace(max_context_tokens=cap))
        ),
    )
    return AppRuntime.effective_context_tokens(fake, "m")


class TestEffectiveBudget:
    def test_zero_cap_follows_the_model_window(self):

        assert budget(1_000_000, 0) == 1_000_000
        assert budget(131_072, 0) == 131_072

    def test_positive_cap_limits_the_window(self):

        assert budget(1_000_000, 65_536) == 65_536

    def test_cap_larger_than_window_is_ignored(self):





        assert budget(32_768, 1_000_000) == 32_768

    def test_unknown_model_falls_back_to_cap(self):
        assert budget(None, 65_536) == 65_536

    def test_unknown_model_without_cap_uses_conservative_default(self):

        assert budget(None, 0) == FALLBACK_TOKENS


class TestSettingsDefault:
    def test_default_is_follow_the_model_not_a_fixed_number(self):





        assert AgentSettings().max_context_tokens == 0

    def test_negative_is_rejected(self):

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AgentSettings(max_context_tokens=-1)
