"""找一个"马上能买"的候选：趋势达标 + 现价贴近 MA20 买区。

`screen_v3.py` 按综合分排序，但综合分高的票往往已经涨离 MA20 很远，买不进去。
低仓位时真正要回答的是"现在离买区最近、同时质量够"的是哪些，这个脚本就是干这个。

筛选逻辑：
  1. stage0（主板 / 非 ST / 价格 / 成交额 / 流通市值）
  2. 趋势模板 ≥ --min-trend（默认 24，即 7/8 以上）
  3. 现价距 MA20 的偏离落在 [--near-low, --near-high]（默认 -3% ~ +2%）
  4. 基本面硬门槛：净利同比 ≥ --min-net、营收同比 ≥ --min-rev
  5. 按 趋势分 desc, 距买区 asc 排序

用法：
    python screen_near.py                    # 默认扫 1500 只
    python screen_near.py --limit 2500 --top 15
    python screen_near.py --min-net 10 --near-high 0.04   # 放宽找更多
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime

import pandas as pd

import data_sources as ds  # noqa: F401  (screen_v3 内部也用同一份)
import screen_v3 as sv


def main() -> None:
    ap = argparse.ArgumentParser(description="贴近买区的候选（趋势 + MA20 距离 + 基本面）")
    ap.add_argument("--limit", type=int, default=1500, help="按流通市值取前 N 只扫描")
    ap.add_argument("--min-amt-yi", type=float, default=0.3, help="20 日均额下限（亿元）")
    ap.add_argument("--min-trend", type=int, default=24, help="趋势分下限（满 32）")
    ap.add_argument("--near-low", type=float, default=-0.03, help="距 MA20 下沿（-0.03 = 低 3%%）")
    ap.add_argument("--near-high", type=float, default=0.02, help="距 MA20 上沿（0.02 = 高 2%%）")
    ap.add_argument("--min-net", type=float, default=20.0, help="净利同比下限 %%")
    ap.add_argument("--min-rev", type=float, default=10.0, help="营收同比下限 %%")
    ap.add_argument("--top", type=int, default=10, help="输出条数")
    args = ap.parse_args()

    print(f"拉全市场列表 …", flush=True)
    uni = sv.fetch_universe()

    # 不用 stage0 的成交额过滤：盘中跑的时候 universe 里的 amount 是"当日已成交额"，
    # 早盘只有几十亿分之一，会把绝大多数票误杀。这里只用板块/ST/价格/流通市值，
    # 成交额改用 20 日均额（amt20）在拿到 K 线后再筛。
    d = uni.copy()
    d = d[~d["name"].astype(str).str.contains("ST|退", na=False)]
    d = d[d["price"].between(sv.PRICE_MIN, sv.PRICE_MAX)]
    d = d[d["floatcap"].fillna(0) >= 3e9]
    bad = ("688", "689", "300", "301", "8", "4", "9")
    d = d[~d["code"].astype(str).str.startswith(bad)]
    assert not d["code"].astype(str).str.startswith(("688", "689", "300", "301")).any(), "板块过滤失效！"

    cand = d.sort_values("floatcap", ascending=False).head(args.limit)
    print(f"  过滤后 {len(d)} 只，按流通市值扫描前 {len(cand)} 只", flush=True)

    min_amt = args.min_amt_yi * 1e8
    rows: list[dict] = []
    for i, r in enumerate(cand.itertuples(), 1):
        if i % 100 == 0:
            print(f"  …{i}/{len(cand)}  命中 {len(rows)}", flush=True)
        k = sv.kline(r.code)
        if k is None:
            continue
        t = sv.trend_score(k)
        if t is None or t["trend_score"] < args.min_trend:
            continue
        if t["amt20"] < min_amt:
            continue
        ma20 = t["ma20"]
        if ma20 <= 0:
            continue
        dist = t["last"] / ma20 - 1
        if not (args.near_low <= dist <= args.near_high):
            continue
        rows.append({
            "code": r.code,
            "name": r.name,
            "price": round(float(t["last"]), 2),
            "trend": t["trend_score"],
            "ma20": round(float(ma20), 2),
            "dist_pct": round(dist * 100, 2),
            "buy_low": round(ma20 * 0.995, 2),
            "buy_high": round(ma20 * 1.02, 2),
            "stop": round(ma20 * 0.97, 2),
            "target": round(t["high60"] * 1.002, 2),
            "ret120": round(t["ret120"] * 100, 1),
            "amt20_yi": round(t["amt20"] / 1e8, 2),
        })

    print(f"\n趋势 ≥{args.min_trend}/32 且距 MA20 在 {args.near_low:+.0%}~{args.near_high:+.0%} 的：{len(rows)} 只")

    # 基本面只对命中的跑，避免把 F10 打到限流
    passed: list[dict] = []
    for row in rows:
        g = sv.f10_growth(row["code"])
        net, rev = g.get("yoy_net"), g.get("yoy_rev")
        row["yoy_net"] = None if net is None else round(float(net), 1)
        row["yoy_rev"] = None if rev is None else round(float(rev), 1)
        row["roe"] = None if g.get("roe") is None else round(float(g["roe"]), 1)
        if net is None or rev is None:
            row["gate"] = "无数据"
            continue
        if net >= args.min_net and rev >= args.min_rev:
            row["gate"] = "过"
            passed.append(row)
        else:
            row["gate"] = "未过"

    print(f"基本面（净利 ≥{args.min_net:.0f}% 且营收 ≥{args.min_rev:.0f}%）后：{len(passed)} 只\n")

    passed.sort(key=lambda x: (-x["trend"], abs(x["dist_pct"])))
    out = passed[: args.top]

    if out:
        print(f"{'代码':<8}{'名称':<10}{'现价':>7}{'趋势':>5}{'MA20':>8}{'距MA20':>8}{'买区':>15}{'止损':>7}{'目标':>7}{'净利%':>7}")
        for r in out:
            print(f"{r['code']:<8}{r['name']:<10}{r['price']:>7.2f}{r['trend']:>5}"
                  f"{r['ma20']:>8.2f}{r['dist_pct']:>7.2f}%{r['buy_low']:>7.2f}-{r['buy_high']:<7.2f}"
                  f"{r['stop']:>7.2f}{r['target']:>7.2f}{r['yoy_net']:>7.1f}")
    else:
        print("没有同时满足『趋势 + 贴近 MA20 + 基本面』的标的。")

    LOGS = sv.Path("data/logs") if hasattr(sv, "Path") else None
    from pathlib import Path
    LOGS = Path("data/logs")
    LOGS.mkdir(parents=True, exist_ok=True)
    p = LOGS / f"screen_near_{datetime.now():%Y%m%d}.json"
    p.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "params": vars(args),
        "near": rows,
        "passed": passed,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果写入 {p}")


if __name__ == "__main__":
    main()
