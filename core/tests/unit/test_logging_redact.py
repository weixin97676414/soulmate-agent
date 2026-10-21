








from __future__ import annotations

import logging
import sys

from my_agent.observability.logger import ConsoleFormatter, JsonFormatter


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








        jwt = "eyJhbGciOiJIUzI1NiJ9.hs879xyz"

        line = ConsoleFormatter().format(
            _record("请求失败", exc_info=_exc_info(f"Authorization: Bearer {jwt}"))
        )

        assert "Bearer <TOKEN>" in line
        assert jwt not in line

    def test_traceback_secret_is_gone_whatever_rule_wins(self):

        line = ConsoleFormatter().format(
            _record("请求失败", exc_info=_exc_info(f"Authorization: Bearer {SECRET}"))
        )

        
        
        assert SECRET not in line
        assert "<" in line  

    def test_redaction_can_be_disabled(self):

        line = ConsoleFormatter(redact_enabled=False).format(_record(f"key={SECRET}"))

        assert SECRET in line

    def test_non_secret_text_is_untouched(self):

        line = ConsoleFormatter().format(_record("连接 127.0.0.1:8080 成功"))

        assert "127.0.0.1:8080" in line


class TestJsonFormatter:
    def test_message_and_exception_are_redacted(self):
        record = _record(f"配置错误: {SECRET}", exc_info=_exc_info(f"token={SECRET}"))

        line = JsonFormatter().format(record)

        assert "<API_KEY>" in line
        assert SECRET not in line

    def test_extra_fields_are_redacted(self):

        record = _record("导出配置")
        record.extra = {"model_key": SECRET}

        line = JsonFormatter().format(record)

        assert SECRET not in line


class TestNoFormatterBypassesRedaction:


    def test_every_formatter_redacts_by_default(self):
        for formatter in (ConsoleFormatter(), JsonFormatter()):
            line = formatter.format(_record(f"token={SECRET}"))
            assert SECRET not in line, f"{type(formatter).__name__} 没有脱敏"
