"""结构化日志。

对应《智能体框架开发文档》11.2 节。输出 JSON 行，便于检索；
所有消息在落盘前统一脱敏。
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ..security.redact import redact

CONFIGURED = False


class JsonFormatter(logging.Formatter):
    def __init__(self, *, redact_enabled: bool = True) -> None:
        super().__init__()
        self._redact_enabled = redact_enabled

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage(), enabled=self._redact_enabled),
        }
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            data.update({k: redact(str(v), enabled=self._redact_enabled) for k, v in extra.items()})
        if record.exc_info:
            data["exc"] = redact(
                self.formatException(record.exc_info), enabled=self._redact_enabled
            )
        return json.dumps(data, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """开发模式下的可读输出。

    ## 为什么这里也要脱敏

    控制台 handler 走的是 stderr。它没有 JsonFormatter 那样的结构化处理，
    一度被当成"反正只是屏幕上的东西"而漏掉了 ``redact`` —— 但 Electron 会把
    子进程的 stderr 收进自己的日志、开发模式下还会直接打到终端上。
    **屏幕/终端缓冲/被复制走的日志，和落盘文件一样会泄漏**，
    只是省去了攻击者读文件的那一步。

    ``JsonFormatter`` 早就做了，这里补上才能保证"任何出口都过一遍 redact"。
    """

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[41m",
    }
    RESET = "\033[0m"

    def __init__(self, *, redact_enabled: bool = True) -> None:
        super().__init__()
        self._redact_enabled = redact_enabled

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        msg = redact(record.getMessage(), enabled=self._redact_enabled)
        line = f"{color}{ts} [{record.levelname[0]}]{self.RESET} {record.name} | {msg}"
        # 异常的 traceback 里同样可能带上密钥（例如 httpx 把带 Authorization 的
        # 请求上下文打出来），不能只脱敏 msg
        if record.exc_info:
            line += "\n" + redact(
                self.formatException(record.exc_info), enabled=self._redact_enabled
            )
        return line


def setup_logging(
    *,
    level: str = "INFO",
    logs_dir: Path | None = None,
    console: bool = True,
    redact_enabled: bool = True,
) -> None:
    """初始化根 logger。重复调用是幂等的。"""
    global CONFIGURED
    if CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)

    if console:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(ConsoleFormatter(redact_enabled=redact_enabled))
        root.addHandler(stream)

    if logs_dir is not None:
        logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            logs_dir / "core.log",
            when="midnight",
            backupCount=14,
            encoding="utf-8",
        )
        file_handler.setFormatter(JsonFormatter(redact_enabled=redact_enabled))
        root.addHandler(file_handler)

    # 第三方库降噪
    for noisy in ("httpx", "httpcore", "uvicorn.access", "mcp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
