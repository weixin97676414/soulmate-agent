



















from __future__ import annotations

from typing import Any

DEFAULT_LINE = "cn"

ENDPOINTS: dict[str, dict[str, Any]] = {
    "cn": {
        
        "page_base": "https://china.xinjianxue.com",
        
        "api_base": "https://china.xinjianxue.com",
        
        "redeem_base": ["https://chinaapi.xinjianxue.com", "https://api.xinjianxue.com"],
        
        
        
        
        "report_base": "https://china.xinjianxue.com",
    },
    "seoul": {
        "page_base": "https://www.xinjianxue.com",
        "api_base": "https://www.xinjianxue.com",
        "redeem_base": ["https://www.xinjianxue.com"],
        "report_base": "https://www.xinjianxue.com",
    },
}


def endpoints_for(line: str | None) -> dict[str, Any]:

    key = (line or DEFAULT_LINE).strip().lower()
    return ENDPOINTS.get(key, ENDPOINTS[DEFAULT_LINE])


def library_url(line: str | None) -> str:

    return f"{endpoints_for(line)['page_base']}/buddy.html"


def report_base(line: str | None) -> str:







    return str(endpoints_for(line)["report_base"])


__all__ = ["DEFAULT_LINE", "ENDPOINTS", "endpoints_for", "library_url", "report_base"]
