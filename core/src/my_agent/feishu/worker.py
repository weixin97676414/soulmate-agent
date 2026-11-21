



































from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, TextIO


ENV_APP_ID = "AGENT_FEISHU_APP_ID"
ENV_APP_SECRET = "AGENT_FEISHU_APP_SECRET"
ENV_BOT_ID = "AGENT_FEISHU_BOT_ID"


def _emit(payload: dict[str, Any], out: TextIO) -> None:

    out.write(json.dumps(payload, ensure_ascii=False) + "\n")
    out.flush()


class _LarkLogBridge(logging.Handler):
















    def __init__(self, out: TextIO, bot_id: str, level: int = logging.INFO) -> None:
        super().__init__(level=level)
        self._out = out
        self._bot_id = bot_id

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = record.getMessage()
        except Exception:  
            return
        _emit(
            {
                "kind": "log",
                "bot_id": self._bot_id,
                "level": record.levelname.lower(),
                "text": text[:500],
            },
            self._out,
        )


def run() -> int:

    app_id = (os.environ.get(ENV_APP_ID) or "").strip()
    app_secret = (os.environ.get(ENV_APP_SECRET) or "").strip()
    bot_id = (os.environ.get(ENV_BOT_ID) or "").strip()

    
    protocol_out = sys.stdout
    sys.stdout = sys.stderr

    if not app_id or not app_secret:
        _emit(
            {"kind": "error", "bot_id": bot_id, "message": "缺少 App ID / App Secret"},
            protocol_out,
        )
        return 2

    try:
        import lark_oapi as lark
    except ImportError as exc:  
        _emit(
            {"kind": "error", "bot_id": bot_id, "message": f"没有安装 lark-oapi：{exc}"},
            protocol_out,
        )
        return 3

    def on_message(event: Any) -> None:





        try:
            raw = lark.JSON.marshal(event)
            payload = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        except Exception as exc:  
            _emit(
                {"kind": "error", "bot_id": bot_id, "message": f"事件解析失败：{exc}"},
                protocol_out,
            )
            return
        _emit({"kind": "event", "bot_id": bot_id, "payload": payload}, protocol_out)

    
    
    
    
    
    
    
    
    
    
    
    
    debug_level = (
        logging.DEBUG if (os.environ.get("AGENT_FEISHU_DEBUG") or "").strip() else logging.INFO
    )
    lark_logger = logging.getLogger("Lark")
    lark_logger.addHandler(_LarkLogBridge(protocol_out, bot_id, level=debug_level))
    lark_logger.setLevel(debug_level)

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )
    client = lark.ws.Client(app_id, app_secret, event_handler=handler)

    _emit({"kind": "ready", "bot_id": bot_id}, protocol_out)
    try:
        client.start()
    except Exception as exc:  
        _emit({"kind": "error", "bot_id": bot_id, "message": str(exc)}, protocol_out)
        return 4
    return 0


if __name__ == "__main__":  
    raise SystemExit(run())
