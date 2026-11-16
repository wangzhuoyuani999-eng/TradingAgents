"""Smoke-test the keyless data path: no LLM involved, just vendors."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradingagents  # noqa: F401  (loads .env from the working directory)
from tradingagents.dataflows.router import route_to_vendor


def probe(name, fn):
    started = time.time()
    try:
        out = fn()
        elapsed = time.time() - started
        text = out if isinstance(out, str) else str(out)
        print(f"[OK]   {name:<14} {elapsed:6.1f}s  {len(text):>6} chars")
        print("       " + text[:240].replace("\n", " | "))
    except Exception as exc:  # noqa: BLE001 - a probe reports whatever happens
        print(f"[FAIL] {name:<14} {time.time() - started:6.1f}s  {type(exc).__name__}: {exc}")


print(f"proxy env: HTTP_PROXY={os.environ.get('HTTP_PROXY')!r} HTTPS_PROXY={os.environ.get('HTTPS_PROXY')!r}")
probe("stock_data", lambda: route_to_vendor("get_stock_data", "NVDA", "2026-10-01", "2026-10-31"))
probe("indicators", lambda: route_to_vendor("get_indicators", "NVDA", "rsi", "2026-10-31", 30))
probe("news", lambda: route_to_vendor("get_news", "NVDA", "2026-10-01", "2026-10-31"))
probe("fundamentals", lambda: route_to_vendor("get_fundamentals", "NVDA", "2026-10-31"))
probe("insider", lambda: route_to_vendor("get_insider_transactions", "NVDA"))
