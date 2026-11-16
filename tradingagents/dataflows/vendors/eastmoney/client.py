"""Eastmoney HTTP client for A-share prices, fundamentals, flows and news.

Yahoo Finance is the pipeline's default vendor, but it is unreachable or
rate-limited from this network and carries thin coverage for mainland listings
(news returns zero articles, ``.info`` 404s). Eastmoney's public quote/F10/news
endpoints answer reliably for ``.SS`` / ``.SZ`` symbols, so this vendor supplies
the same tool surface for A-shares and lets the router fall back to Yahoo for
everything else.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import requests

from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}

_MARKET = {"SS": "1", "SH": "1", "SZ": "0", "BJ": "0"}

QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
FLOW_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
F10_URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
SEARCH_URL = "https://search-api-web.eastmoney.com/search/jsonp"
NOTICE_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"
FAST_NEWS_URL = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"


def is_cn_symbol(symbol: str) -> bool:
    """Whether ``symbol`` looks like a Shanghai/Shenzhen/Beijing listing."""
    code, _, market = symbol.strip().upper().partition(".")
    return market in _MARKET and len(code) == 6 and code.isdigit()


def to_secid(symbol: str) -> str:
    code, _, market = symbol.strip().upper().partition(".")
    return f"{_MARKET[market]}.{code}"


def bare_code(symbol: str) -> str:
    return symbol.strip().upper().partition(".")[0]


def secucode(symbol: str) -> str:
    """Eastmoney's datacenter id, e.g. 600036.SH (Yahoo writes .SS)."""
    code, _, market = symbol.strip().upper().partition(".")
    return f"{code}.{'SH' if market in ('SS', 'SH') else 'SZ'}"


def _get(url: str, params: dict, timeout: int = 15) -> requests.Response:
    try:
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp
    except requests.RequestException as exc:  # network, DNS, proxy, status
        raise VendorUnavailableError(f"Eastmoney request failed for {url}: {exc}") from exc


def _json(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except ValueError as exc:
        raise VendorUnavailableError(f"Eastmoney returned non-JSON: {resp.text[:120]}") from exc


def quote(symbol: str, fields: str | None = None) -> dict:
    """Live (or last-session) quote snapshot."""
    fields = fields or (
        "f43,f44,f45,f46,f47,f48,f57,f58,f60,f116,f117,f162,f167,f168,f169,f170"
    )
    data = _json(_get(QUOTE_URL, {"secid": to_secid(symbol), "fields": fields})).get("data")
    if not data:
        raise NoMarketDataError(symbol, symbol, "Eastmoney returned no quote payload")
    return data


def company_name(symbol: str) -> str:
    return quote(symbol, "f58").get("f58") or symbol


def kline(
    symbol: str,
    beg: str = "20200101",
    end: str = "20991231",
    adjust: int = 1,
) -> list[dict]:
    """Daily bars, forward-adjusted (``adjust=1``) to match yfinance auto_adjust."""
    payload = _json(
        _get(
            KLINE_URL,
            {
                "secid": to_secid(symbol),
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57",
                "klt": "101",
                "fqt": str(adjust),
                "beg": beg,
                "end": end,
            },
        )
    )
    data = payload.get("data") or {}
    rows = []
    for line in data.get("klines") or []:
        p = line.split(",")
        rows.append(
            {
                "date": p[0],
                "open": float(p[1]),
                "close": float(p[2]),
                "high": float(p[3]),
                "low": float(p[4]),
                "volume": int(float(p[5]) * 100),  # 手 -> 股
                "amount": float(p[6]),
            }
        )
    return rows


def f10_reports(symbol: str, size: int = 8) -> list[dict]:
    """Main financial indicators, newest report first."""
    payload = _json(
        _get(
            F10_URL,
            {
                "reportName": "RPT_F10_FINANCE_MAINFINADATA",
                "columns": "ALL",
                "filter": f'(SECUCODE="{secucode(symbol)}")',
                "pageNumber": 1,
                "pageSize": size,
                "sortTypes": -1,
                "sortColumns": "REPORT_DATE",
            },
        )
    )
    return (payload.get("result") or {}).get("data") or []


def money_flow(symbol: str, days: int = 10) -> list[dict]:
    """Daily main-capital flow (主力 = 超大单 + 大单), oldest first."""
    payload = _json(
        _get(
            FLOW_URL,
            {
                "lmt": "0",
                "klt": "101",
                "secid": to_secid(symbol),
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
            },
        )
    )
    data = payload.get("data") or {}
    rows = []
    for line in data.get("klines") or []:
        p = line.split(",")
        rows.append(
            {
                "date": p[0],
                "main_net": float(p[1]),        # 主力净流入 (元)
                "small_net": float(p[2]),
                "mid_net": float(p[3]),
                "large_net": float(p[4]),
                "xlarge_net": float(p[5]),
                "main_pct": float(p[6]),        # 主力净占比 %
                "close": float(p[11]),
                "change_pct": float(p[12]),
            }
        )
    return rows[-days:]


def _strip_jsonp(text: str) -> dict:
    match = re.search(r"\((.*)\)\s*$", text, re.S)
    raw = match.group(1) if match else text
    return json.loads(raw)


def search_news(keyword: str, size: int = 20) -> list[dict]:
    """Eastmoney article search, newest first."""
    payload = {
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "time",
                "pageIndex": 1,
                "pageSize": size,
                "preTag": "",
                "postTag": "",
            }
        },
    }
    resp = _get(SEARCH_URL, {"cb": "x", "param": json.dumps(payload, ensure_ascii=False)})
    data = _strip_jsonp(resp.text)
    return (data.get("result") or {}).get("cmsArticleWebOld") or []


def announcements(symbol: str, size: int = 20) -> list[dict]:
    """Company filings (公告), newest first."""
    payload = _json(
        _get(
            NOTICE_URL,
            {
                "sr": -1,
                "page_size": size,
                "page_index": 1,
                "ann_type": "A",
                "client_source": "web",
                "stock_list": bare_code(symbol),
            },
        )
    )
    return ((payload.get("data") or {}).get("list")) or []


def fast_news(size: int = 30) -> list[dict]:
    """Market-wide 7x24 newswire."""
    payload = _json(
        _get(
            FAST_NEWS_URL,
            {
                "client": "web",
                "biz": "web_724",
                "fastColumn": "102",
                "sortEnd": "",
                "pageSize": str(size),
                "req_trace": "1",
            },
        )
    )
    return ((payload.get("data") or {}).get("fastNewsList")) or []


def today_local() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
