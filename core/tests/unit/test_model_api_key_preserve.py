"""``_preserve_api_keys`` 的回归测试。

这里锁住的是一个**真实发生过的**故障：用户在设置页点一次「保存」，
模型就连不上了，重启又好。

根因是两处脱敏掩码格式不一致（Electron 侧是「前 3 位 + 4 个星」，
Python 侧是「前 4 位 + 6 个星」），而"用户有没有改过这个 Key"的判断
当时**只**依赖掩码字符串精确相等 —— 于是"没改过"被判成"改过了"，
掩码串被当成真 Key 写进 ``models.json``。

现在的主判据换成了请求里显式的 ``api_key_unchanged`` 标记，不再依赖
任何格式约定；掩码比对退化为兜底。
"""

from __future__ import annotations

from my_agent.config.schemas import ModelsConfig, ModelSpec
from my_agent.server.routes.models import _preserve_api_keys

REAL_KEY = "sk-realsecret1234567890"


def _spec(model_id: str, api_key: str) -> ModelSpec:
    return ModelSpec(id=model_id, model_name=model_id, adapter="openai_compat", api_key=api_key)


def _config(api_key: str) -> ModelsConfig:
    return ModelsConfig(default_model="m1", models=[_spec("m1", api_key)])


def test_explicit_unchanged_restores_key() -> None:
    """显式声明「没改过」时，即使提交值是一串别的东西也要还原成真 Key。

    这一条是对旧实现的直接超越：旧实现要求提交值**恰好等于**旧掩码，
    格式一变就整体失效。
    """
    old = _config(REAL_KEY)
    new = _config("sk-****7890")
    new.models[0].api_key_unchanged = True

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == REAL_KEY


def test_mask_submitted_without_flag_is_still_restored() -> None:
    """兜底：老前端原样回传掩码（没带标记）时仍要能认出来。"""
    old = _config(REAL_KEY)
    new = _config(old.models[0].masked_api_key())

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == REAL_KEY


def test_empty_without_flag_keeps_key() -> None:
    """**留空且没带任何标记，也必须保住旧 Key。**

    ⚠️ 这一条的**期望值被反转了**，值得记一笔。

    旧实现把"提交空值且未声明 unchanged"解释成"用户明确要删除"，理由是
    "否则用户永远删不掉一个填错的 Key"。那个理由当时看着成立，但它把一个
    **删除动作**藏进了一个**几乎无法观测的信号**里：前端只要在某一刻提交了
    空串（密钥库条目缺失、注入时机、明文回填的 IPC 竞态、has_api_key 恰好
    是 false……），密钥就被真的抹掉。

    用户的原话是"不知道操作了什么，密钥又被清空了，模型无法使用"。
    几轮修下来结论很清楚：**"空值"根本不该承载"删除"这个语义。**
    删除必须是用户能看见、能确认的显式动作（``clear_api_key``，界面上
    是「清除密钥」按钮 + 二次确认）。
    """
    old = _config(REAL_KEY)
    new = _config("")

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == REAL_KEY, "空值绝不能清除密钥"


def test_explicit_clear_flag_is_the_only_way_to_delete() -> None:
    """**唯一**能删掉密钥的路径：显式带上 ``clear_api_key``。"""
    old = _config(REAL_KEY)
    new = _config("")
    new.models[0].clear_api_key = True

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == ""


def test_explicit_clear_wins_over_a_submitted_value() -> None:
    """显式清除时，即使还夹带了一个值也以"清除"为准（界面不会这么发，但语义要明确）。"""
    old = _config(REAL_KEY)
    new = _config("sk-still-here")
    new.models[0].clear_api_key = True

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == ""


def test_clear_flag_is_never_persisted() -> None:
    """``clear_api_key`` 同样是请求元数据，绝不写进 models.json。"""
    old = _config(REAL_KEY)
    new = _config("")
    new.models[0].clear_api_key = True

    result = _preserve_api_keys(old, new)

    assert result.models[0].clear_api_key is False
    assert "clear_api_key" not in result.models[0].model_dump()


def test_new_value_overwrites_old_key() -> None:
    """用户真的填了新值就用新值（这是"用户自己修改"的正当代路径）。"""
    old = _config(REAL_KEY)
    new = _config("sk-brand-new-key")

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == "sk-brand-new-key"


def test_empty_with_flag_keeps_key() -> None:
    """**留空 + 声明「没改过」必须保住旧 Key。**

    这是设置页自动保存**最常走**的那条路：输入框里没有新值（用户没动它，
    或页面刷新把它重建为空），但条目本身是"已配置"的 —— 前端于是提交
    ``api_key=""`` 配 ``api_key_unchanged=true``。

    这一条守的是用户反复反馈过的现象："我去点了下页面别处，Key 就没了"。
    只要这一条成立，任何一次"空值提交"都不会毁掉已配好的 Key。
    """
    old = _config(REAL_KEY)
    new = _config("")
    new.models[0].api_key_unchanged = True

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == REAL_KEY, "空值 + unchanged 标记必须保留原 Key"


def test_empty_with_flag_on_unconfigured_model_stays_empty() -> None:
    """本来就没有 Key 的条目：留空 + 标记不该凭空造出一个 Key 来。"""
    old = ModelsConfig(default_model="m1", models=[_spec("m1", "")])
    new = _config("")
    new.models[0].api_key_unchanged = True

    result = _preserve_api_keys(old, new)

    assert result.get("m1").api_key == ""


def test_new_model_keeps_submitted_key() -> None:
    """新加的模型没有旧值可还原，提交什么就是什么（误标了也不该被弄坏）。"""
    old = _config(REAL_KEY)
    new = ModelsConfig(
        default_model="m2",
        models=[_spec("m1", REAL_KEY), _spec("m2", "sk-new")],
    )
    new.models[1].api_key_unchanged = True

    result = _preserve_api_keys(old, new)

    assert result.get("m2").api_key == "sk-new"


def test_unchanged_flag_is_never_persisted() -> None:
    """标记是**请求元数据**，不能留在配置对象上、更不该写进 models.json。"""
    old = _config(REAL_KEY)
    new = _config("")
    new.models[0].api_key_unchanged = True

    result = _preserve_api_keys(old, new)

    assert result.models[0].api_key_unchanged is False
    assert "api_key_unchanged" not in result.models[0].model_dump()


def test_mask_format_is_stable() -> None:
    """锁住脱敏格式。

    它必须与 ``desktop/electron/secrets.ts`` 的 ``maskSecret()`` 一致：
    **前 4 位 + 6 个星 + 后 4 位**。改了这边就必须同步改那边（反之亦然）——
    两边漂移过一次，代价是上面描述的那个线上故障。
    """
    assert _spec("m1", REAL_KEY).masked_api_key() == "sk-r******7890"
    # 太短的值截取头尾会几乎还原出原文，所以整体打码
    assert _spec("m2", "short").masked_api_key() == "*****"
    assert _spec("m3", "").masked_api_key() == ""
