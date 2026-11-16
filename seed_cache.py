"""Seed the TradingAgents price cache from Eastmoney (Yahoo is rate-limited).

Writes data/cache/<TICKER>-YFin-data.csv in the yfinance shape the loader
expects, then touches the file so the 15-minute freshness check passes.
"""
import os
import sys

import pandas as pd
import requests

SYMBOLS = {
    "601899.SS": "1.601899",
    "002415.SZ": "0.002415",
    "600030.SS": "1.600030",
    "601166.SS": "1.601166",
    "002241.SZ": "0.002241",
    "600111.SS": "1.600111",
    "002602.SZ": "0.002602",
}

CACHE = "data/cache"
BEGIN, END = "20211101", "20261231"


def fetch(secid: str) -> pd.DataFrame:
    resp = requests.get(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "klt": "101",
            "fqt": "1",  # 前复权, comparable to yfinance auto_adjust
            "beg": BEGIN,
            "end": END,
        },
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()["data"]
    rows = []
    for line in payload["klines"]:
        p = line.split(",")
        rows.append(
            [p[0], float(p[1]), float(p[3]), float(p[4]), float(p[2]), int(float(p[5]) * 100)]
        )
    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = df["Date"] + " 00:00:00+08:00"
    return df


def main() -> None:
    os.makedirs(CACHE, exist_ok=True)
    for ticker, secid in SYMBOLS.items():
        df = fetch(secid)
        path = os.path.join(CACHE, f"{ticker}-YFin-data.csv")
        df.to_csv(path, index=False, encoding="utf-8")
        os.utime(path, None)
        last = df.iloc[-1]
        print(f"{ticker}: rows={len(df)} last={last['Date'][:10]} C={last['Close']:.2f} "
              f"V={last['Volume']/1e6:.1f}M first={df.iloc[0]['Date'][:10]}")
        # sanity: no gaps in the last 5 sessions
        print("   ", " | ".join(f"{r.Date[5:10]} {r.Close:.2f}" for r in df.tail(5).itertuples()))


if __name__ == "__main__":
    sys.exit(main())
