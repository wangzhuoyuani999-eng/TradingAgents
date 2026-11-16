"""Eastmoney vendor for mainland A-share listings (.SS / .SZ / .BJ)."""

from tradingagents.dataflows.vendors.eastmoney.fundamentals import get_fundamentals
from tradingagents.dataflows.vendors.eastmoney.news import get_global_news, get_news
from tradingagents.dataflows.vendors.eastmoney.stock import get_stock_data

__all__ = ["get_stock_data", "get_fundamentals", "get_news", "get_global_news"]
