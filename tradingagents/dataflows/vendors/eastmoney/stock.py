"""Daily OHLCV for A-shares from Eastmoney."""

from __future__ import annotations

from typing import Annotated

from tradingagents.dataflows.errors import NoMarketDataError

from .client import is_cn_symbol, kline


def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):
    """Daily bars between ``start_date`` and ``end_date`` (inclusive), CSV body."""
    if not is_cn_symbol(symbol):
        raise NoMarketDataError(symbol, symbol, "Eastmoney covers A-shares only")

    rows = [r for r in kline(symbol, start_date.replace("-", ""), end_date.replace("-", ""))
            if r["date"] <= end_date]
    if not rows:
        raise NoMarketDataError(symbol, symbol, f"no bars between {start_date} and {end_date}")

    header = (
        f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
        f"# Total records: {len(rows)}\n"
        f"# Source: Eastmoney, forward-adjusted (前复权)\n\n"
    )
    body = ["Date,Open,High,Low,Close,Volume"]
    body += [
        f"{r['date']},{r['open']:.2f},{r['high']:.2f},{r['low']:.2f},{r['close']:.2f},{r['volume']}"
        for r in rows
    ]
    return header + "\n".join(body)
