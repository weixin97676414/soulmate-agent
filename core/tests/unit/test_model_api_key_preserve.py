













from __future__ import annotations

from my_agent.config.schemas import ModelsConfig, ModelSpec
from my_agent.server.routes.models import _preserve_api_keys

REAL_KEY = "sk-realsecret1234567890"


def _spec(model_id: str, api_key: str) -> ModelSpec:
    return ModelSpec(id=model_id, model_name=model_id, adapter="openai_compat", api_key=api_key)


def _config(api_key: str) -> ModelsConfig:
    return ModelsConfig(default_model="m1", models=[_spec("m1", api_key)])


def test_explicit_unchanged_restores_key() -> None:





    old = _config(REAL_KEY)
    new = _config("sk-****7890")
    new.models[0].api_key_unchanged = True

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == REAL_KEY


def test_mask_submitted_without_flag_is_still_restored() -> None:

    old = _config(REAL_KEY)
    new = _config(old.models[0].masked_api_key())

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == REAL_KEY


def test_empty_without_flag_keeps_key() -> None:















    old = _config(REAL_KEY)
    new = _config("")

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == REAL_KEY, "空值绝不能清除密钥"


def test_explicit_clear_flag_is_the_only_way_to_delete() -> None:

    old = _config(REAL_KEY)
    new = _config("")
    new.models[0].clear_api_key = True

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == ""


def test_explicit_clear_wins_over_a_submitted_value() -> None:

    old = _config(REAL_KEY)
    new = _config("sk-still-here")
    new.models[0].clear_api_key = True

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == ""


def test_clear_flag_is_never_persisted() -> None:

    old = _config(REAL_KEY)
    new = _config("")
    new.models[0].clear_api_key = True

    result = _preserve_api_keys(old, new)

    assert result.models[0].clear_api_key is False
    assert "clear_api_key" not in result.models[0].model_dump()


def test_new_value_overwrites_old_key() -> None:

    old = _config(REAL_KEY)
    new = _config("sk-brand-new-key")

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == "sk-brand-new-key"


def test_empty_with_flag_keeps_key() -> None:









    old = _config(REAL_KEY)
    new = _config("")
    new.models[0].api_key_unchanged = True

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == REAL_KEY, "空值 + unchanged 标记必须保留原 Key"


def test_empty_with_flag_on_unconfigured_model_stays_empty() -> None:

    old = ModelsConfig(default_model="m1", models=[_spec("m1", "")])
    new = _config("")
    new.models[0].api_key_unchanged = True

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == ""


def test_new_model_keeps_submitted_key() -> None:

    old = _config(REAL_KEY)
    new = ModelsConfig(
        default_model="m2",
        models=[_spec("m1", REAL_KEY), _spec("m2", "sk-new")],
    )
    new.models[1].api_key_unchanged = True

    result = _preserve_api_keys(old, new)

    assert result.get("m2").api_key == "sk-new"


def test_unchanged_flag_is_never_persisted() -> None:

    old = _config(REAL_KEY)
    new = _config("")
    new.models[0].api_key_unchanged = True

    result = _preserve_api_keys(old, new)

    assert result.models[0].api_key_unchanged is False
    assert "api_key_unchanged" not in result.models[0].model_dump()


def test_mask_format_is_stable() -> None:






    assert _spec("m1", REAL_KEY).masked_api_key() == "sk-r******7890"
    
    assert _spec("m2", "short").masked_api_key() == "*****"
    assert _spec("m3", "").masked_api_key() == ""
