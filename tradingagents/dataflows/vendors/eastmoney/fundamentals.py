"""A-share fundamentals from Eastmoney F10 plus capital-flow context."""

from __future__ import annotations

from typing import Annotated

from tradingagents.dataflows.errors import NoMarketDataError

from .client import (
    company_name,
    f10_reports,
    is_cn_symbol,
    money_flow,
    quote,
    today_local,
)


def _yi(value, digits: int = 2) -> str:
    """A CNY amount rendered in 亿元."""
    if value is None:
        return "—"
    return f"{value / 1e8:,.{digits}f} 亿元"


def _pct(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}%"


def _num(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None,
):
    """Company overview: valuation snapshot, latest report, and 5-day money flow.

    Point-in-time safe: a past ``as_of_date`` only reads reports whose
    announcement date is on or before it, and drops the live quote/flow, which
    carry no historical vintage.
    """
    if not is_cn_symbol(ticker):
        raise NoMarketDataError(ticker, ticker, "Eastmoney fundamentals cover A-shares only")

    reports = f10_reports(ticker, 12)
    if as_of_date:
        reports = [r for r in reports if (r.get("NOTICE_DATE") or "")[:10] <= as_of_date]
    if not reports:
        raise NoMarketDataError(
            ticker, ticker, f"no financial report announced on or before {as_of_date or 'today'}"
        )
    report = reports[0]

    lines = [f"Name: {company_name(ticker)}", f"Symbol: {ticker.upper()}"]

    live = not as_of_date or as_of_date >= today_local()
    if live:
        q = quote(ticker)
        price = (q.get("f43") or 0) / 100
        lines += [
            f"Last Price: {price:.2f} CNY",
            f"Market Cap: {_yi(q.get('f116'))}",
            f"Float Market Cap: {_yi(q.get('f117'))}",
            f"PE (TTM): {_num((q.get('f162') or 0) / 100 if q.get('f162') else None)}",
            f"PB: {_num((q.get('f167') or 0) / 100 if q.get('f167') else None)}",
            f"Turnover Rate: {_pct((q.get('f168') or 0) / 100 if q.get('f168') else None)}",
        ]

    lines += [
        "",
        f"Latest Report: {report.get('REPORT_DATE_NAME') or report.get('REPORT_TYPE')} "
        f"(announced {(report.get('NOTICE_DATE') or '')[:10]})",
        f"Revenue (累计): {_yi(report.get('TOTALOPERATEREVE'))} "
        f"(YoY {_pct(report.get('TOTALOPERATEREVETZ'))})",
        f"Net Profit (归母): {_yi(report.get('PARENTNETPROFIT'))} "
        f"(YoY {_pct(report.get('PARENTNETPROFITTZ'))})",
        f"EPS (基本): {_num(report.get('EPSJB'))} CNY",
        f"BPS (每股净资产): {_num(report.get('BPS'))} CNY",
        f"ROE (加权): {_pct(report.get('ROEJQ'))}",
        f"Gross Margin: {_pct(report.get('XSMLL'))}",
        f"Debt/Asset: {_pct(report.get('ZCFZL'))}",
        f"Operating Cash Flow (累计): {_yi(report.get('NETCASH_OPERATE_PK'))}",
    ]

    if live:
        flow = money_flow(ticker, 5)
        if flow:
            lines += ["", "Capital Flow (主力净流入, last 5 sessions):"]
            for row in flow:
                lines.append(
                    f"- {row['date']}: {row['main_net'] / 1e8:+.2f} 亿元 "
                    f"({row['main_pct']:+.2f}% of turnover), close {row['close']:.2f} "
                    f"({row['change_pct']:+.2f}%)"
                )
            total = sum(r["main_net"] for r in flow) / 1e8
            lines.append(f"- 5-day total: {total:+.2f} 亿元")

    return f"# Company Fundamentals for {ticker.upper()}\n\n" + "\n".join(lines)
