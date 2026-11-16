"""A-share coverage probe: what does the data layer actually return for .SS/.SZ?"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradingagents  # noqa: F401  (loads .env)
import yfinance as yf

TICKERS = [
    "600519.SS", "300750.SZ", "002594.SZ", "601318.SS",
    "600036.SS", "000858.SZ", "601899.SS", "688981.SS",
    "000001.SS", "399001.SZ",
]

for t in TICKERS:
    started = time.time()
    try:
        df = yf.Ticker(t).history(period="1mo", interval="1d", auto_adjust=False)
        if df.empty:
            print(f"{t:<12} EMPTY")
            continue
        last = df.iloc[-1]
        chg = (last["Close"] / df.iloc[-2]["Close"] - 1) * 100
        print(f"{t:<12} rows={len(df):>2} last={last['Close']:.2f} chg={chg:+.2f}% "
              f"vol={last['Volume']/1e6:.0f}M  {time.time()-started:.1f}s")
    except Exception as exc:  # noqa: BLE001
        print(f"{t:<12} FAIL {type(exc).__name__}: {str(exc)[:90]}")

print("\n--- news coverage ---")
for t in ("600519.SS", "300750.SZ"):
    try:
        n = yf.Ticker(t).news or []
        print(f"{t}: {len(n)} articles", (n[0].get("title", "")[:60] if n else ""))
    except Exception as exc:  # noqa: BLE001
        print(f"{t}: FAIL {type(exc).__name__}")
