"""日志脱敏：任何出口都要过一遍 ``redact``。

``ConsoleFormatter`` 一度是唯一没有脱敏的出口（理由大致是"反正只是打到屏幕上"），
但 Electron 会把核心的 stderr 收进自己的日志、开发模式下还会直接显示在终端里，
屏幕和终端缓冲同样会被整段复制走。

这组用例保证**所有** formatter 都脱敏，防止将来新增出口时又漏一个。
"""

from __future__ import annotations

import logging
import sys

from my_agent.observability.logger import ConsoleFormatter, JsonFormatter

# 命中 redact.py 里「厂商 API Key 前缀」规则的最小样例
SECRET = "sk-abcdef1234567890"


def _record(msg: str, **kwargs) -> logging.LogRecord:
    kwargs.setdefault("exc_info", None)
    return logging.LogRecord(
        name="my_agent.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        **kwargs,
    )


def _exc_info(message: str):
    try:
        raise ValueError(message)
    except ValueError:
        return sys.exc_info()


class TestConsoleFormatter:
    def test_message_is_redacted(self):
        line = ConsoleFormatter().format(_record(f"加载失败: {SECRET}"))

        assert "<API_KEY>" in line
        assert SECRET not in line

    def test_exception_traceback_is_redacted(self):
        """异常堆栈里同样可能夹带密钥，不能只脱敏 msg。

        httpx 之类的库在报错时会把请求上下文打出来，Authorization 头就在里面。

        刻意用一个**不带** ``sk-`` 前缀的令牌：``PATTERNS`` 里 key 前缀规则排在
        bearer 规则之前，给个 ``sk-`` 的样例会先被替换成 ``<API_KEY>``，
        断言就得写成"两种结果之一"，反而掩盖了真正要保证的东西。
        """
        jwt = "eyJhbGciOiJIUzI1NiJ9.hs879xyz"

        line = ConsoleFormatter().format(
            _record("请求失败", exc_info=_exc_info(f"Authorization: Bearer {jwt}"))
        )

        assert "Bearer <TOKEN>" in line
        assert jwt not in line

    def test_traceback_secret_is_gone_whatever_rule_wins(self):
        """换个前缀再验一次：结果必须是「原文消失」，不依赖具体哪条规则命中。"""
        line = ConsoleFormatter().format(
            _record("请求失败", exc_info=_exc_info(f"Authorization: Bearer {SECRET}"))
        )

        # 上面那条用例给了 jwt，这条给 sk- 前缀；两者最终形态不同，
        # 但共同的不变量是——原始密钥不会出现在输出里。
        assert SECRET not in line
        assert "<" in line  # 发生过替换，不是整段被丢掉

    def test_redaction_can_be_disabled(self):
        """本地排查时需要看原始值，所以开关仍然保留。"""
        line = ConsoleFormatter(redact_enabled=False).format(_record(f"key={SECRET}"))

        assert SECRET in line

    def test_non_secret_text_is_untouched(self):
        """别把正常日志改坏——脱敏过度同样会让排查失去依据。"""
        line = ConsoleFormatter().format(_record("连接 127.0.0.1:8080 成功"))

        assert "127.0.0.1:8080" in line


class TestJsonFormatter:
    def test_message_and_exception_are_redacted(self):
        record = _record(f"配置错误: {SECRET}", exc_info=_exc_info(f"token={SECRET}"))

        line = JsonFormatter().format(record)

        assert "<API_KEY>" in line
        assert SECRET not in line

    def test_extra_fields_are_redacted(self):
        """结构化日志的 extra 字段也是一条出口。"""
        record = _record("导出配置")
        record.extra = {"model_key": SECRET}

        line = JsonFormatter().format(record)

        assert SECRET not in line


class TestNoFormatterBypassesRedaction:
    """防止将来新增的 formatter 漏掉脱敏。"""

    def test_every_formatter_redacts_by_default(self):
        for formatter in (ConsoleFormatter(), JsonFormatter()):
            line = formatter.format(_record(f"token={SECRET}"))
            assert SECRET not in line, f"{type(formatter).__name__} 没有脱敏"
