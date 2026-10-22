












from __future__ import annotations

from my_agent.memory.long_term import LongTermMemory


_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def scoped(namespace: str) -> str:
    return LongTermMemory._scoped_collection("knowledge", namespace)


def assert_legal(name: str) -> None:

    assert 3 <= len(name) <= 512, f"长度越界: {name}"
    assert set(name) <= _ALLOWED, f"含非法字符: {name}"
    assert name[0].isascii() and name[0].isalnum(), f"首字符非法: {name}"
    assert name[-1].isascii() and name[-1].isalnum(), f"尾字符非法: {name}"


def test_ascii_id_stays_unchanged() -> None:

    assert scoped("soulmate") == "assistant_soulmate"
    assert scoped("LoveBuddy") == "assistant_LoveBuddy"
    assert scoped("group_g1") == "assistant_group_g1"


def test_chinese_id_is_made_legal() -> None:

    name = scoped("文爱伴侣-e07b0a")
    assert_legal(name)
    
    assert name != "knowledge"
    assert name.startswith("assistant_")


def test_all_chinese_id_falls_back_to_hash_and_stays_unique() -> None:

    a = scoped("文爱伴侣")
    b = scoped("另一个名字")
    assert_legal(a)
    assert_legal(b)
    assert a != b, "两个中文搭子共用同一个库 = 记忆互相串味"
    
    assert a == scoped("文爱伴侣")


def test_missing_namespace_falls_back_to_base() -> None:

    assert scoped("") == "knowledge"
    assert scoped("   ") == "knowledge"


def test_namespace_only_punctuation_still_legal() -> None:

    assert_legal(scoped("---"))
    assert_legal(scoped("。。"))
