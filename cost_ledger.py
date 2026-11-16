"""Cost ledger for TradingAgents runs, priced with DeepSeek's official rates.

Rates are CNY per 1M tokens, from https://api-docs.deepseek.com/zh-cn/quick_start/pricing

    deepseek-flash   cache hit  0.02 off-peak / 0.04 peak
                     cache miss 1.00 off-peak / 2.00 peak
                     output     4.00 off-peak / 8.00 peak

Peak hours are Beijing time Mon-Fri 09:00-12:00 and 14:00-18:00 (public holidays
are not modelled; a holiday run is billed at the off-peak rate here).

The run log records only total input tokens, not the cached share, so the ledger
reports an upper bound (every input token billed as a miss) and an estimate that
assumes CACHE_HIT_RATIO of the prompt was served from cache.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime

import pandas as pd

PRICING = {
    "deepseek-flash": {
        "hit": {"peak": 0.04, "off": 0.02},
        "miss": {"peak": 2.00, "off": 1.00},
        "out": {"peak": 8.00, "off": 4.00},
    },
    "deepseek-v4-pro": {
        "hit": {"peak": 0.30, "off": 0.15},
        "miss": {"peak": 9.00, "off": 4.50},
        "out": {"peak": 27.00, "off": 13.50},
    },
}

CACHE_HIT_RATIO = 0.60
STATS = "data/logs/run_stats.jsonl"
LEDGER = "data/logs/cost_ledger.csv"


def is_peak(ts: datetime) -> bool:
    if ts.weekday() >= 5:  # Sat/Sun
        return False
    m = ts.hour * 60 + ts.minute
    return (9 * 60 <= m < 12 * 60) or (14 * 60 <= m < 18 * 60)


def rate_for(model: str) -> dict:
    for key in PRICING:
        if key in (model or ""):
            return PRICING[key]
    return PRICING["deepseek-flash"]


def cost_cny(tokens_in: int, tokens_out: int, model: str, ts: datetime) -> tuple[float, float, float]:
    """(upper_bound_all_miss, estimate_with_cache, lower_bound_all_hit) in CNY."""
    r = rate_for(model)
    band = "peak" if is_peak(ts) else "off"
    upper = tokens_in / 1e6 * r["miss"][band] + tokens_out / 1e6 * r["out"][band]
    lower = tokens_in / 1e6 * r["hit"][band] + tokens_out / 1e6 * r["out"][band]
    est = (tokens_in / 1e6) * (r["miss"][band] * (1 - CACHE_HIT_RATIO) + r["hit"][band] * CACHE_HIT_RATIO) \
        + tokens_out / 1e6 * r["out"][band]
    return round(upper, 4), round(est, 4), round(lower, 4)


def load_runs() -> pd.DataFrame:
    rows = []
    with open(STATS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            ts = datetime.fromisoformat(r["generated_at"])
            rows.append({
                "time": ts.strftime("%Y-%m-%d %H:%M"),
                "date": r.get("date"),
                "ticker": r.get("ticker"),
                "analysts": "+".join(r.get("analysts") or []),
                "model": r.get("quick_think_llm") or r.get("llm_provider"),
                "in": int(r.get("tokens_in") or 0),
                "out": int(r.get("tokens_out") or 0),
                "calls": r.get("llm_calls"),
                "secs": r.get("elapsed_seconds"),
                "peak": is_peak(ts),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    costs = df.apply(lambda r: cost_cny(r["in"], r["out"], r["model"], datetime.strptime(r["time"], "%Y-%m-%d %H:%M")), axis=1)
    df["cny_upper"], df["cny_est"], df["cny_lower"] = zip(*costs)
    return df


def write_ledger(df: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    df.to_csv(LEDGER, index=False, encoding="utf-8-sig")


def main() -> None:
    df = load_runs()
    if df.empty:
        print("no runs recorded yet")
        return
    write_ledger(df)

    print(f"{'时间':<17}{'代码':<11}{'分析师':<24}{'输入':>8}{'输出':>8}"
          f"{'高峰':>4}{'上限(元)':>10}{'估算(元)':>10}")
    for _, r in df.iterrows():
        who = r["analysts"][:22]
        print(f"{r['time']:<17}{r['ticker']:<11}{who:<24}"
              f"{r['in']:>8,}{r['out']:>8,}{'是' if r['peak'] else '否':>4}"
              f"{r['cny_upper']:>10.2f}{r['cny_est']:>10.2f}")

    print()
    print(f"合计 {len(df)} 次分析：输入 {df['in'].sum():,} tokens，输出 {df['out'].sum():,} tokens")
    print(f"费用上限（输入全部按缓存未命中）：{df['cny_upper'].sum():.2f} 元")
    print(f"费用估算（缓存命中率 {CACHE_HIT_RATIO:.0%}）：{df['cny_est'].sum():.2f} 元")
    print(f"费用下限（输入全部命中缓存）：{df['cny_lower'].sum():.2f} 元")
    by_day = df.groupby("date")["cny_est"].sum().sort_index()
    print("\n按日（估算）：" + "，".join(f"{d} {v:.2f}元" for d, v in by_day.items()))
    today = datetime.now().strftime("%Y-%m-%d")
    t = df[df["time"].str.startswith(today)]
    if not t.empty:
        print(f"\n今日（{today}）：{len(t)} 次分析，估算 {t['cny_est'].sum():.2f} 元（上限 {t['cny_upper'].sum():.2f} 元）")
    print(f"\n明细已写入 {LEDGER}")


if __name__ == "__main__":
    sys.exit(main())
