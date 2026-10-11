"""记忆库名的合法性（第 103 批补）。

## 为什么值得单独一个文件

它守的是一条**曾经真实发生过的故障**：搭子叫「文爱伴侣」（中文名），拼出来的
chromadb 库名是 ``assistant_文爱伴侣-e07b0a`` —— 而 chromadb 只接受
``[a-zA-Z0-9._-]``，于是建库失败，**那个搭子的长期记忆整个不可用**。
界面上只说"长期记忆当前不可用"，提示还指着"开关 / 依赖"两条无关的原因，查不出来。

根因是净化函数用了 ``str.isalnum()``：它**对中文也返回 True**，
所以"字符集收窄"这句话在代码里从来没成立过。
"""

from __future__ import annotations

from my_agent.memory.long_term import LongTermMemory

#: chromadb 的库名规则：3~512 个字符、只含 `[a-zA-Z0-9._-]`、首尾必须是字母或数字。
_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def scoped(namespace: str) -> str:
    return LongTermMemory._scoped_collection("knowledge", namespace)


def assert_legal(name: str) -> None:
    """按 chromadb 的规则逐条断言（这几条任何一条不满足，建库都会直接失败）。"""
    assert 3 <= len(name) <= 512, f"长度越界: {name}"
    assert set(name) <= _ALLOWED, f"含非法字符: {name}"
    assert name[0].isascii() and name[0].isalnum(), f"首字符非法: {name}"
    assert name[-1].isascii() and name[-1].isalnum(), f"尾字符非法: {name}"


def test_ascii_id_stays_unchanged() -> None:
    """纯 ASCII 的 id 原样保留 —— 老用户的库名不能变（等于换了一个库、老记忆全查不到）。"""
    assert scoped("soulmate") == "assistant_soulmate"
    assert scoped("LoveBuddy") == "assistant_LoveBuddy"
    assert scoped("group_g1") == "assistant_group_g1"


def test_chinese_id_is_made_legal() -> None:
    """中文 id（实测踩过的那个形态）必须产出合法库名。"""
    name = scoped("文爱伴侣-e07b0a")
    assert_legal(name)
    # ⚠️ 也不能退化成 base：那会让所有中文搭子共用同一个库、记忆互相串味
    assert name != "knowledge"
    assert name.startswith("assistant_")


def test_all_chinese_id_falls_back_to_hash_and_stays_unique() -> None:
    """整串都非 ASCII 时用摘要兜底，且不同 id 不会撞成同一个库。"""
    a = scoped("文爱伴侣")
    b = scoped("另一个名字")
    assert_legal(a)
    assert_legal(b)
    assert a != b, "两个中文搭子共用同一个库 = 记忆互相串味"
    # 同一个 id 必须每次得到同一个名字：否则重启一次就换一个库，老记忆查不到
    assert a == scoped("文爱伴侣")


def test_missing_namespace_falls_back_to_base() -> None:
    """没有 namespace 时用调用方给的库名（知识库默认 `knowledge`）—— 这是既有语义，不许改。"""
    assert scoped("") == "knowledge"
    assert scoped("   ") == "knowledge"


def test_namespace_only_punctuation_still_legal() -> None:
    """净化后什么都不剩的情况（全是标点）也不能产出非法名。"""
    assert_legal(scoped("---"))
    assert_legal(scoped("。。"))
