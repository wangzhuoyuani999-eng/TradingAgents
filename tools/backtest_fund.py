"""把「基本面硬门槛」纳入回测，回答一个问题：
    净利同比 ≥+20% 且 营收同比 ≥+10% 这道门槛，到底是在帮忙还是在砍机会？

背景（2026-11-27）：`research/策略迭代日志.md` 的 v1.0 明确写着
「回测未使用财务门槛（F10 只有最新一期，无法按公告日对齐）」
——也就是生产里最凶的一层（只剩 0–1 只候选）**从来没有回测背书**。

做法（无未来函数）：
  - 趋势信号与交易模拟完全复用 `backtest_v3.py`（同一套 8/8 模板、T+1 开盘入场、破 MA20 或满 20 日离场）；
  - 财务数据按**公告可用日**取，不用「最新一期」：
      报告期 03-31 → 04-30 可用；06-30 → 08-31；09-30 → 10-31；12-31 → 次年 04-30
    这是法定披露截止日，属于最保守的可获得性假设（不用先知）。
  - 在同一批交易上叠加不同门槛，比较：交易数 / 胜率 / 平均收益 / PF / 累计收益 / 最大回撤。

用法：
    .venv/Scripts/python.exe tools/backtest_fund.py                # 4 组门槛对比
    .venv/Scripts/python.exe tools/backtest_fund.py --limit 60     # 快速试跑
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import backtest_v3 as bt  # noqa: E402

CACHE = ROOT / "data" / "cache" / "fundamentals"
F10 = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
MAX_POS = 3

# 报告期 -> 法定披露截止日（月, 日, 年偏移）
DEADLINE = {
    "03-31": (4, 30, 0),
    "06-30": (8, 31, 0),
    "09-30": (10, 31, 0),
    "12-31": (4, 30, 1),
}

VARIANTS = [
    ("趋势 only（基线，无门槛无择时）", None, None, False),
    ("趋势 + 门槛 20/10", 20.0, 10.0, False),
    ("趋势 + 放宽 10/5", 10.0, 5.0, False),
    ("趋势 + 只要数据 0/0", 0.0, 0.0, False),
    ("趋势 + 大盘择时", None, None, True),
    ("趋势 + 门槛 20/10 + 大盘择时（当前生产）", 20.0, 10.0, True),
]


def secu(code: str) -> str:
    return f"{code}.SH" if code.startswith("6") else f"{code}.SZ"


def fetch_history(code: str) -> list[dict]:
    """拉某只股票最近几年的主要财务指标（净利/营收同比），带本地缓存。"""
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{code}.json"
    if cached.exists():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except Exception:
            pass
    out: list[dict] = []
    for attempt in range(3):
        try:
            r = requests.get(F10, params={
                "reportName": "RPT_F10_FINANCE_MAINFINADATA",
                "columns": "ALL",
                "filter": f'(SECUCODE="{secu(code)}")',
                "pageNumber": 1,
                "pageSize": 28,
                "sortColumns": "REPORT_DATE",
                "sortTypes": -1,
            }, headers={"User-Agent": "Mozilla/5.0"}, timeout=12).json()
            rows = ((r.get("result") or {}).get("data") or [])
            for row in rows:
                out.append({
                    "report_date": str(row.get("REPORT_DATE") or "")[:10],
                    "yoy_net": row.get("PARENTNETPROFITTZ"),
                    "yoy_rev": row.get("TOTALOPERATEREVETZ"),
                })
            break
        except Exception:
            time.sleep(0.8 * (attempt + 1))
    cached.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def available_on(report_date: str) -> str:
    """报告期 -> 按法定截止日计算的可获得日（保守，无未来函数）。"""
    if len(report_date) < 10:
        return "9999-12-31"
    year, md = int(report_date[:4]), report_date[5:10]
    if md not in DEADLINE:
        return "9999-12-31"
    m, d, off = DEADLINE[md]
    return f"{year + off:04d}-{m:02d}-{d:02d}"


def gate_ok(history: list[dict], date: str, min_net: float | None, min_rev: float | None) -> tuple[bool, dict]:
    """在 date 当天，用「已披露」的最新一期财务判断门槛。"""
    usable = [h for h in history if available_on(h["report_date"]) <= date]
    if not usable:
        return False, {}
    latest = max(usable, key=lambda h: h["report_date"])
    if min_net is None:
        return True, latest
    net = latest.get("yoy_net")
    rev = latest.get("yoy_rev")
    if net is None or rev is None:
        return False, latest
    return (float(net) >= min_net and float(rev) >= min_rev), latest


def portfolio_stats(trades: pd.DataFrame) -> dict:
    """最多同时持 MAX_POS 只、每只 1/MAX_POS 资金，按时间顺序占用空位。"""
    if trades.empty:
        return {"trades": 0, "win_rate": 0.0, "avg": 0.0, "pf": 0.0, "cum": 0.0, "mdd": 0.0}
    t = trades.sort_values("entry_date").reset_index(drop=True)
    busy: list[str] = []
    taken = []
    for row in t.itertuples():
        busy = [d for d in busy if d > str(row.entry_date)]
        if len(busy) < MAX_POS:
            taken.append(row)
            busy.append(str(row.exit_date))
    pt = pd.DataFrame(taken)
    if pt.empty:
        return {"trades": 0, "win_rate": 0.0, "avg": 0.0, "pf": 0.0, "cum": 0.0, "mdd": 0.0}
    eq = [1.0]
    for r in pt["ret"]:
        eq.append(eq[-1] * (1 + r / MAX_POS))
    eqs = pd.Series(eq[1:])
    peak = eqs.cummax()
    wins = pt[pt["ret"] > 0]
    losses = pt[pt["ret"] <= 0]
    pf = (wins["ret"].sum() / abs(losses["ret"].sum())) if len(losses) else float("inf")
    return {
        "trades": int(len(pt)),
        "signals": int(len(trades)),
        "win_rate": round(float(len(wins) / len(pt)), 4),
        "avg": round(float(pt["ret"].mean()), 4),
        "pf": round(float(pf), 2),
        "cum": round(float(eqs.iloc[-1] - 1), 4),
        "mdd": round(float((eqs / peak - 1).min()), 4),
    }


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="基本面门槛回测")
    ap.add_argument("--limit", type=int, default=150, help="股票池大小（按成交额）")
    ap.add_argument("--out", default="data/logs/backtest_fund.json")
    args = ap.parse_args()

    t0 = time.time()
    uni = bt.fetch_universe(args.limit)
    print(f"股票池 {len(uni)} 只")

    raw: list[dict] = []
    histories: dict[str, list[dict]] = {}
    for idx, row in enumerate(uni.itertuples(), 1):
        df = bt.kline(row.code)
        if df is None:
            continue
        trades = bt.run_stock(row.code, row.name, df)
        if not trades:
            continue
        hist = fetch_history(row.code)
        histories[row.code] = hist
        for tr in trades:
            tr["signal_date"] = str(tr["entry_date"])[:10]
            ok_cache: dict[str, bool] = {}
            tr["fund"] = {label: gate_ok(hist, tr["signal_date"], mn, mr)[0]
                          for label, mn, mr, _need_timing in VARIANTS if mn is not None}
            raw.append(tr)
        if idx % 25 == 0:
            print(f"  …{idx}/{len(uni)} 累计信号 {len(raw)}")

    if not raw:
        print("没有信号，无法比较。")
        return 1

    t = pd.DataFrame(raw)
    print(f"\n趋势信号合计 {len(t)} 笔（{t['entry_date'].min()} ~ {t['entry_date'].max()}）")

    regime = bt.index_regime()
    t["bull"] = t["signal_date"].map(lambda d: bool(regime.get(str(d)[:10], False)))
    print(f"信号发生时上证在 MA200 上方：{t['bull'].mean() * 100:.1f}%")

    rows = []
    for label, mn, mr, need_timing in VARIANTS:
        sub = t
        if mn is not None:
            sub = sub[sub["fund"].map(lambda d: d.get(label, False))]
        if need_timing:
            sub = sub[sub["bull"]]
        st = portfolio_stats(sub)
        rows.append({"variant": label, "min_net": mn, "min_rev": mr, **st})
        print(f"  {label:38s} 信号 {st.get('signals', 0):4d}  成交 {st['trades']:4d}  "
              f"胜率 {st['win_rate']*100:5.1f}%  均值 {st['avg']*100:+.2f}%  "
              f"PF {st['pf']:5.2f}  累计 {st['cum']*100:+7.1f}%  回撤 {st['mdd']*100:6.1f}%")

    out = {
        "generated_at": datetime.now().isoformat(),
        "universe": int(len(uni)),
        "signals_total": int(len(t)),
        "period": [str(t["entry_date"].min()), str(t["entry_date"].max())],
        "variants": rows,
    }
    path = ROOT / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n用时 {time.time() - t0:.0f}s，结果写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
