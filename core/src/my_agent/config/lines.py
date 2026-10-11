"""线路端点表：同一个"线路"在不同用途上对应的**域名并不相同**。

## 为什么要有这张表

客户端有两条线路（大陆 / 首尔），而每条线路上：

- **官网搭子库页面**与**账号接口**都在 `china.xinjianxue.com` / `www.xinjianxue.com`；
- **兑换码接口**在大陆是**另外两个域名**（`chinaapi` / `api`，见后端文档
  《兑换码充值Token-前端接入说明》，产品要求按文档给的域名走）。

散在各处写死的话，改一个域名要翻好几个文件、还容易漏掉一处。所以集中在这里，
由**主进程把当前线路同步进来**（`PUT /v1/client/line`），核心据此挑域名。

## 兑换码为什么是"主 + 备"两个

文档里大陆给了两个域名。按序试，**只有连不上（网络层失败）才切下一个** ——
"兑换码已被使用 / 不存在"这类业务错误绝不能重试：码是一次性核销的，
重试只会让用户以为系统出错（见 `desktop/electron/account/api.ts`）。
"""

from __future__ import annotations

from typing import Any

DEFAULT_LINE = "cn"

ENDPOINTS: dict[str, dict[str, Any]] = {
    "cn": {
        # 官网搭子库页面（AI 查"官网有没有合适的搭子"用）
        "page_base": "https://china.xinjianxue.com",
        # 既有的账号接口域名
        "api_base": "https://china.xinjianxue.com",
        # 兑换码：后端文档给的大陆域名，主 + 备
        "redeem_base": ["https://chinaapi.xinjianxue.com", "https://api.xinjianxue.com"],
        # 心鉴学"报告"接口（Soulmate 专用 / 人际关系运营 这两个内置技能调的）
        #
        # 四份 SKILL.md 里把它写死成 `china.xinjianxue.com`，与官网 / 账号同域；
        # 集中到这里是为了"改域名只改一处"（现在的惯例）。
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
    """取某条线路的端点表；线路不认识时退回默认线路（不抛错）。"""
    key = (line or DEFAULT_LINE).strip().lower()
    return ENDPOINTS.get(key, ENDPOINTS[DEFAULT_LINE])


def library_url(line: str | None) -> str:
    """官网搭子库的地址（按线路）。"""
    return f"{endpoints_for(line)['page_base']}/buddy.html"


def report_base(line: str | None) -> str:
    """心鉴学"报告"接口的域名（按线路）。

    单独开一个函数而不是让调用点去翻 ``ENDPOINTS``：心鉴学那两个内置技能是
    **按线路二选一**的（见 ``skill/builtin/xjx.py``），域名取错线路就等于
    拿着大陆的凭证去国际站请求、必然 401 —— 这种错不会说清原因，
    所以入口只留一个。
    """
    return str(endpoints_for(line)["report_base"])


__all__ = ["DEFAULT_LINE", "ENDPOINTS", "endpoints_for", "library_url", "report_base"]
