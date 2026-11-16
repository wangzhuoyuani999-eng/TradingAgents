"""Independent technical snapshot for the A-share batch (cross-check, not the agent's view)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradingagents  # noqa: F401  (loads .env / proxy)
import numpy as np
import pandas as pd
import yfinance as yf

NAMES = {
    "600519.SS": "贵州茅台", "000858.SZ": "五粮液", "300750.SZ": "宁德时代",
    "002594.SZ": "比亚迪", "601318.SS": "中国平安", "600036.SS": "招商银行",
    "601899.SS": "紫金矿业", "688981.SS": "中芯国际", "002415.SZ": "海康威视",
    "600276.SS": "恒瑞医药",
}
INDEX = {"000001.SS": "上证指数", "399001.SZ": "深证成指", "399006.SZ": "创业板指"}


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def atr(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


rows = []
for t, name in {**NAMES, **INDEX}.items():
    try:
        df = yf.Ticker(t).history(period="1y", interval="1d", auto_adjust=False)
        df = df.dropna()
        if len(df) < 70:
            print(f"{t} too short ({len(df)})")
            continue
        c = df["Close"]
        rows.append({
            "ticker": t, "name": name, "close": c.iloc[-1],
            "d1": (c.iloc[-1] / c.iloc[-2] - 1) * 100,
            "d5": (c.iloc[-1] / c.iloc[-6] - 1) * 100,
            "d20": (c.iloc[-1] / c.iloc[-21] - 1) * 100,
            "ma20": c.rolling(20).mean().iloc[-1],
            "ma60": c.rolling(60).mean().iloc[-1],
            "rsi14": rsi(c).iloc[-1],
            "atr14": atr(df).iloc[-1],
            "high60": c.iloc[-60:].max(),
            "low60": c.iloc[-60:].min(),
            "volratio": df["Volume"].iloc[-5:].mean() / df["Volume"].iloc[-60:].mean(),
        })
    except Exception as exc:  # noqa: BLE001
        print(f"{t} FAIL {type(exc).__name__}: {exc}")

out = pd.DataFrame(rows)
out["vs_ma20"] = (out.close / out.ma20 - 1) * 100
out["vs_ma60"] = (out.close / out.ma60 - 1) * 100
out["atr_pct"] = out.atr14 / out.close * 100
out["pos_60d"] = (out.close - out.low60) / (out.high60 - out.low60) * 100
pd.set_option("display.width", 200, "display.max_columns", 30)
print(out[["ticker", "name", "close", "d1", "d5", "d20", "vs_ma20", "vs_ma60",
           "rsi14", "atr_pct", "pos_60d", "volratio"]].round(2).to_string(index=False))
out.to_csv("data/ashare_snapshot.csv", index=False, encoding="utf-8-sig")
print("\nsaved data/ashare_snapshot.csv")
