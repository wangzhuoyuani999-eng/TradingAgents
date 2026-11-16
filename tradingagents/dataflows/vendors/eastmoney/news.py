"""A-share company news and filings from Eastmoney, plus the 7x24 newswire."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from tradingagents.dataflows.errors import NoMarketDataError

from .client import (
    announcements,
    bare_code,
    company_name,
    fast_news,
    is_cn_symbol,
    search_news,
)


def _day(value: str) -> str:
    return (value or "")[:10]


def _within(day: str, start: str, end: str) -> bool:
    return bool(day) and start <= day <= end


def get_news(
    ticker: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):
    """Articles and filings about ``ticker`` published in the window."""
    if not is_cn_symbol(ticker):
        raise NoMarketDataError(ticker, ticker, "Eastmoney news covers A-shares only")

    name = company_name(ticker)
    articles = search_news(name, 30)
    filings = announcements(ticker, 20)

    items = []
    for a in articles:
        day = _day(a.get("date"))
        if not _within(day, start_date, end_date):
            continue
        items.append(
            {
                "day": day,
                "title": (a.get("title") or "").strip(),
                "summary": (a.get("content") or "").strip(),
                "source": (a.get("mediaName") or "东方财富").strip(),
                "link": a.get("url") or "",
                "kind": "news",
            }
        )
    for f in filings:
        day = _day(f.get("notice_date") or f.get("display_time"))
        if not _within(day, start_date, end_date):
            continue
        title = (f.get("title") or "").strip()
        items.append(
            {
                "day": day,
                "title": title,
                "summary": "公司公告",
                "source": "交易所公告",
                "link": f"https://data.eastmoney.com/notices/detail/{bare_code(ticker)}/"
                        f"{f.get('art_code')}.html",
                "kind": "filing",
            }
        )

    if not items:
        return (
            f"<Eastmoney returned no articles or filings about {name} ({ticker}) between "
            f"{start_date} and {end_date}. Its search index covers a recent sample of "
            f"articles, so this is not proof the company had no news.>"
        )

    items.sort(key=lambda i: i["day"], reverse=True)
    lines = [f"## {ticker} News, from {start_date} to {end_date}:", ""]
    for item in items[:40]:
        lines.append(f"[{item['day']}] {item['title']}")
        lines.append(f"Type: {'公司公告' if item['kind'] == 'filing' else '财经报道'} | Source: {item['source']}")
        if item["summary"]:
            lines.append(f"Summary: {item['summary']}")
        if item["link"]:
            lines.append(f"Link: {item['link']}")
        lines.append("")
    return "\n".join(lines)


def get_global_news(
    as_of_date: Annotated[str, "current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "days to look back"] = None,
    limit: Annotated[int, "max articles"] = None,
):
    """Market-wide 7x24 newswire items from the look-back window."""
    look_back = look_back_days or 3
    max_items = limit or 20
    end = datetime.strptime(as_of_date, "%Y-%m-%d")
    start = end - timedelta(days=look_back)
    start_day, end_day = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    items = []
    for row in fast_news(60):
        day = _day(row.get("showTime"))
        if _within(day, start_day, end_day):
            items.append(row)

    if not items:
        return (
            f"<Eastmoney 7x24 newswire returned nothing between {start_day} and {end_day}; "
            f"treat market news as unavailable for this window.>"
        )

    lines = [f"## Market News, from {start_day} to {end_day}:", ""]
    for row in items[:max_items]:
        lines.append(f"[{_day(row.get('showTime'))}] {(row.get('title') or '').strip()}")
        summary = (row.get("summary") or "").strip()
        if summary:
            lines.append(f"Summary: {summary}")
        lines.append("")
    return "\n".join(lines)
