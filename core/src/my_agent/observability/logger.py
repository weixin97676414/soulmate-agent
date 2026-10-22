





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

    
    for noisy in ("httpx", "httpcore", "uvicorn.access", "mcp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
