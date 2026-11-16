"""选股策略 v1 的回测：趋势模板 8 条 + 收盘破 MA20 出场。

不做花哨的仓位管理，只回答一个问题：
    「8/8 趋势模板 + 不闪崩」这个过滤条件，在 A 股 2023-2026 有没有正期望？

方法（无未来函数）：
  - 信号：T 日收盘满足全部条件；
  - 入场：T+1 日开盘价；
  - 出场：持有的某日收盘跌破 MA20 → 次日开盘卖；或满 20 个交易日 → 当日收盘卖；
  - 同一只股票持仓期间不重复开仓。

输出：交易数、胜率、平均收益、盈亏比、最大单笔亏损、组合净值曲线、基准对比。
"""

from __future__ import annotations

import json
import time
from datetime import datetime

import numpy as np
import pandas as pd

import data_sources as ds

UA = {"User-Agent": "Mozilla/5.0"}
CLIST = "https://push2.eastmoney.com/api/qt/clist/get"
KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"

HOLD_DAYS = 20
UNIVERSE_SIZE = 150


def secid(code: str) -> str:
    return f"1.{code}" if code.startswith(("6", "5")) else f"0.{code}"


def fetch_universe(n: int) -> pd.DataFrame:
    u = ds.universe()
    u["floatcap"] = pd.to_numeric(u["floatcap"], errors="coerce") * 1e4
    u = u[~u["name"].astype(str).str.contains("ST|退", na=False)]
    u = u[~u["code"].astype(str).str.startswith(("688", "689", "8", "4", "9"))]
    return u.sort_values("amount", ascending=False).head(n)


def _old_fetch_universe(n: int) -> pd.DataFrame:
    rows, page = [], 1
    while len(rows) < 900:
        r = requests.get(CLIST, params={
            "pn": page, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2,
            "fid": "f21", "fs": FS, "fields": "f12,f14,f2,f21,f20",
        }, headers=UA, timeout=15).json()
        diff = (r.get("data") or {}).get("diff") or []
        if not diff:
            break
        rows.extend(diff)
        page += 1
        if page > 12:
            break
    df = pd.DataFrame(rows).rename(columns={"f12": "code", "f14": "name", "f2": "price", "f21": "floatcap"})
    df["floatcap"] = pd.to_numeric(df["floatcap"], errors="coerce")
    df["code"] = df["code"].astype(str)
    df = df[~df["name"].astype(str).str.contains("ST|退", na=False)]
    df = df[~df["code"].str.startswith(("688", "689", "8", "4", "9"))]
    df = df.sort_values("floatcap", ascending=False).head(n)
    return df


def kline(code: str) -> pd.DataFrame | None:
    k = ds.kline_qfq(code, 900)
    if k is None or len(k) < 400:
        return None
    k = k.copy()
    if "amount" not in k.columns:
        k["amount"] = k["volume"] * k["close"]
    return k.reset_index(drop=True)


def signals(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"]
    d = pd.DataFrame(index=df.index)
    d["date"] = df["date"]
    d["ma20"] = c.rolling(20).mean()
    d["ma50"] = c.rolling(50).mean()
    d["ma150"] = c.rolling(150).mean()
    d["ma200"] = c.rolling(200).mean()
    d["ma200_prev"] = d["ma200"].shift(20)
    d["low52"] = df["low"].rolling(250).min()
    d["high52"] = df["high"].rolling(250).max()
    d["ret120"] = c / c.shift(120) - 1
    d["crash"] = (c.pct_change() < -0.08).rolling(20).max().fillna(0) > 0

    cond = (
        (c > d["ma150"]) & (c > d["ma200"])
        & (d["ma150"] > d["ma200"])
        & (d["ma200"] > d["ma200_prev"])
        & (d["ma50"] > d["ma150"]) & (d["ma150"] > d["ma200"])
        & (c > d["ma50"])
        & (c / d["low52"] - 1 >= 0.30)
        & (c / d["high52"] - 1 >= -0.25)
        & (~d["crash"])
        & (df["amount"] > 1e8)
    )
    d["signal"] = cond.fillna(False)
    return d


def run_stock(code: str, name: str, df: pd.DataFrame) -> list[dict]:
    s = signals(df)
    trades = []
    i = 260
    n = len(df)
    while i < n - 1:
        if bool(s["signal"].iloc[i]):
            entry_idx = i + 1
            entry = float(df["open"].iloc[entry_idx])
            exit_idx, exit_px, reason = None, None, "timeout"
            for j in range(entry_idx, min(entry_idx + HOLD_DAYS, n - 1)):
                if float(df["close"].iloc[j]) < float(s["ma20"].iloc[j]) and j > entry_idx:
                    exit_idx, exit_px, reason = j + 1, float(df["open"].iloc[j + 1]), "ma20"
                    break
            if exit_idx is None:
                exit_idx = min(entry_idx + HOLD_DAYS, n - 1)
                exit_px, reason = float(df["close"].iloc[exit_idx]), "timeout"
            trades.append({
                "code": code, "name": name,
                "entry_date": df["date"].iloc[entry_idx], "exit_date": df["date"].iloc[exit_idx],
                "entry": round(entry, 2), "exit": round(exit_px, 2),
                "ret": exit_px / entry - 1, "days": exit_idx - entry_idx, "reason": reason,
            })
            i = exit_idx + 1
        else:
            i += 1
    return trades


def index_regime() -> dict:
    """上证指数在 MA200 上方的日期集合（大盘择时过滤）。新浪日线，直连。"""
    try:
        import requests as _rq
        r = _rq.get("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
                    params={"symbol": "sh000001", "scale": 240, "ma": "no", "datalen": 900},
                    headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        data = r.json()
    except Exception:
        return {}
    df = pd.DataFrame(data)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["ma200"] = df["close"].rolling(200).mean()
    df["bull"] = df["close"] > df["ma200"]
    return dict(zip(df["day"], df["bull"]))


def main() -> None:
    t0 = time.time()
    uni = fetch_universe(UNIVERSE_SIZE)
    print(f"股票池 {len(uni)} 只（按流通市值取头部）")

    all_trades, benchmarks = [], []
    for idx, row in enumerate(uni.itertuples(), 1):
        df = kline(row.code)
        if df is None:
            continue
        trades = run_stock(row.code, row.name, df)
        all_trades.extend(trades)
        first, last = float(df["close"].iloc[260]), float(df["close"].iloc[-1])
        benchmarks.append({"code": row.code, "bh": last / first - 1})
        if idx % 25 == 0:
            print(f"  …{idx}/{len(uni)} 累计交易 {len(all_trades)}")

    if not all_trades:
        print("没有产生任何交易信号。")
        return

    t = pd.DataFrame(all_trades)
    regime = index_regime()
    t["bull"] = t["entry_date"].map(lambda d: bool(regime.get(str(d)[:10], False)))
    print(f"\n信号发生时上证在 MA200 上方：{t['bull'].mean() * 100:.1f}%")
    wins = t[t["ret"] > 0]
    losses = t[t["ret"] <= 0]
    pf = wins["ret"].sum() / abs(losses["ret"].sum()) if len(losses) else float("inf")

    print("\n=== 回测结果（趋势模板 8/8，持有≤20日，破MA20离场）===")
    print(f"交易笔数      {len(t)}")
    print(f"胜率          {len(wins) / len(t) * 100:.1f}%")
    print(f"平均每笔      {t['ret'].mean() * 100:+.2f}%")
    print(f"平均盈利      {wins['ret'].mean() * 100:+.2f}%" if len(wins) else "平均盈利      —")
    print(f"平均亏损      {losses['ret'].mean() * 100:+.2f}%" if len(losses) else "平均亏损      —")
    print(f"盈亏比(PF)    {pf:.2f}")
    print(f"平均持有      {t['days'].mean():.1f} 日")
    print(f"最大单笔亏损  {t['ret'].min() * 100:.2f}%")

    # 只在大盘 MA200 上方交易
    t = t[t["bull"]].reset_index(drop=True)
    print(f"\n【加入大盘择时】只保留上证>MA200 期间的信号，剩 {len(t)} 笔")
    if len(t):
        w2 = t[t["ret"] > 0]
        l2 = t[t["ret"] <= 0]
        pf2 = w2["ret"].sum() / abs(l2["ret"].sum()) if len(l2) else float("inf")
        print(f"胜率 {len(w2)/len(t)*100:.1f}%  平均 {t['ret'].mean()*100:+.2f}%  PF {pf2:.2f}")

    # 组合净值：最多同时持有 MAX_POS 只，每只 1/MAX_POS 资金，按时间顺序占用空位
    MAX_POS = 3
    t_sorted = t.sort_values("entry_date").reset_index(drop=True)
    busy_until: list[str] = []
    taken = []
    for row in t_sorted.itertuples():
        busy_until = [d for d in busy_until if d > row.entry_date]
        if len(busy_until) < MAX_POS:
            taken.append(row)
            busy_until.append(str(row.exit_date))
    pt = pd.DataFrame(taken)
    if len(pt):
        # 每笔只占 1/MAX_POS 资金，其余现金；按顺序连乘
        eq = [1.0]
        for r in pt["ret"]:
            eq.append(eq[-1] * (1 + r / MAX_POS))
        eq = pd.Series(eq[1:])
        total = eq.iloc[-1] - 1
        peak = eq.cummax()
        mdd = ((eq / peak) - 1).min()
        print(f"\n满仓上限 {MAX_POS} 只、每只 1/{MAX_POS} 资金：")
        print(f"实际交易      {len(pt)} 笔")
        print(f"累计收益      {total * 100:+.1f}%")
        print(f"最大回撤      {mdd * 100:.1f}%")
    else:
        total, mdd = 0.0, 0.0

    b = pd.DataFrame(benchmarks)
    print(f"\n基准：同池 {len(b)} 只等权买入持有，区间 {b['bh'].mean() * 100:+.1f}%")
    print(f"超额收益      {(total - b['bh'].mean()) * 100:+.1f}%")

    out = {
        "generated_at": datetime.now().isoformat(),
        "universe": len(uni),
        "trades": len(t),
        "win_rate": round(len(wins) / len(t), 4),
        "avg_ret": round(float(t["ret"].mean()), 4),
        "profit_factor": round(float(pf), 2),
        "cum_return": round(float(total), 4),
        "max_drawdown": round(float(mdd), 4),
        "benchmark_bh": round(float(b["bh"].mean()), 4),
        "detail": t_sorted.tail(30).to_dict(orient="records"),
    }
    with open("data/logs/backtest_v3.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n用时 {time.time() - t0:.0f}s，结果写入 data/logs/backtest_v3.json")


if __name__ == "__main__":
    main()
