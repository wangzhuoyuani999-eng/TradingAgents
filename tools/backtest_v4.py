"""回测框架修正版（v4）：固定股票池 + 逐日盯市 + 费用滑点。

修的是 `backtest_v3.py` / `tools/backtest_fund.py` 的两个硬伤：
  1. 池子按「回测当天成交额」抽样 → 每次运行股票集合都漂移，回测不可复现；
     这里把池子**落盘缓存**（`data/cache/bt_pool.json`），同一份池子反复用。
  2. 净值是「每笔 1/3 资金按顺序连乘」的近似 → 路径依赖极强，MDD 不可信；
     这里改成**逐日盯市**：每天先处理卖出（开盘），再处理买入（开盘），最后按收盘价估值，
     得到真正的日度净值曲线、最大回撤与年化。

成本假设（可在参数里调）：
  - 佣金 0.025%（单笔最低 5 元）、印花税 0.05%（仅卖出）、过户费 0.001%（双边）
  - 滑点 0.1%（买入上浮、卖出下调）
  - 100 股整手

已知局限（写进报告，不藏）：
  - 池子是「当前时点的头部股票」，存在**幸存者偏差**（已退市/长期停牌的票不在池内）；
  - 财务数据用法定披露截止日近似可获得性，仍可能早于实际公告；
  - 未考虑涨跌停无法成交、停牌、除权复权误差。

用法：
    .venv/Scripts/python.exe tools/backtest_v4.py                 # 4 个变体对比
    .venv/Scripts/python.exe tools/backtest_v4.py --rebuild-pool  # 重建股票池缓存
    .venv/Scripts/python.exe tools/backtest_v4.py --symbols 30    # 小样本快速试跑
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import data_sources as ds  # noqa: E402
import backtest_fund as bf  # noqa: E402  财务历史 + 门槛（带缓存）

POOL_CACHE = ROOT / "data" / "cache" / "bt_pool.json"
KLINE_CACHE = ROOT / "data" / "cache" / "bt_klines"

COMMISSION = 0.00025
MIN_COMMISSION = 5.0
STAMP_DUTY = 0.0005
TRANSFER = 0.00001
SLIPPAGE = 0.001
HOLD_DAYS = 20
MAX_POS = 3
LIQUIDITY_MIN = 1e8


# ---------------- 数据 ----------------

def load_pool(size: int, rebuild: bool) -> list[dict]:
    """固定股票池（落盘缓存，保证同一份池子可反复回测）。"""
    if POOL_CACHE.exists() and not rebuild:
        cached = json.loads(POOL_CACHE.read_text(encoding="utf-8"))
        if cached.get("size") == size and cached.get("items"):
            print(f"股票池：读缓存 {len(cached['items'])} 只（{cached.get('built_at')}）")
            return cached["items"]
    u = ds.universe()
    u["amount"] = pd.to_numeric(u["amount"], errors="coerce")
    u["floatcap"] = pd.to_numeric(u["floatcap"], errors="coerce") * 1e4
    u = u[~u["name"].astype(str).str.contains("ST|退", na=False)]
    u = u[~u["code"].astype(str).str.startswith(("688", "689", "8", "4", "9"))]
    u = u.sort_values("floatcap", ascending=False).head(size)
    items = [{"code": str(r.code), "name": str(r.name)} for r in u.itertuples()]
    POOL_CACHE.parent.mkdir(parents=True, exist_ok=True)
    POOL_CACHE.write_text(json.dumps(
        {"size": size, "built_at": datetime.now().isoformat(), "rule": "流通市值前 N（剔除ST/科创/创业/北交/B股）",
         "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"股票池：新建 {len(items)} 只并缓存")
    return items


def load_kline(code: str) -> pd.DataFrame | None:
    KLINE_CACHE.mkdir(parents=True, exist_ok=True)
    path = KLINE_CACHE / f"{code}.csv"
    if path.exists():
        df = pd.read_csv(path, dtype={"date": str})
        if len(df) >= 400:
            return df
    k = ds.kline_qfq(code, 900)
    if k is None or len(k) < 400:
        return None
    k = k.copy()
    if "amount" not in k.columns:
        k["amount"] = k["volume"] * k["close"]
    k["date"] = k["date"].astype(str).str[:10]
    k.to_csv(path, index=False)
    return k.reset_index(drop=True)


def with_signals(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"]
    d = df.copy()
    d["ma20"] = c.rolling(20).mean()
    d["ma50"] = c.rolling(50).mean()
    d["ma150"] = c.rolling(150).mean()
    d["ma200"] = c.rolling(200).mean()
    d["ma200_prev"] = d["ma200"].shift(20)
    d["low52"] = df["low"].rolling(250).min()
    d["high52"] = df["high"].rolling(250).max()
    crash = (c.pct_change() < -0.08).rolling(20).max().fillna(0) > 0
    d["signal"] = (
        (c > d["ma150"]) & (c > d["ma200"])
        & (d["ma150"] > d["ma200"])
        & (d["ma200"] > d["ma200_prev"])
        & (d["ma50"] > d["ma150"])
        & (c > d["ma50"])
        & (c / d["low52"] - 1 >= 0.30)
        & (c / d["high52"] - 1 >= -0.25)
        & (~crash)
        & (df["amount"] > LIQUIDITY_MIN)
    ).fillna(False)
    return d


def index_regime(window: int = 200) -> dict:
    """上证在 window 日均线上方的日期集合（window=200 原规则，20 为替代解锁规则）。"""
    try:
        import requests
        r = requests.get(
            "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
            params={"symbol": "sh000001", "scale": 240, "ma": "no", "datalen": 900},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        df = pd.DataFrame(r.json())
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["ma"] = df["close"].rolling(window).mean()
        return dict(zip(df["day"].astype(str).str[:10], (df["close"] > df["ma"]).fillna(False)))
    except Exception:
        return {}


# ---------------- 撮合 ----------------

def buy_cost(price: float, shares: int) -> float:
    amount = price * shares
    return amount + max(MIN_COMMISSION, amount * COMMISSION) + amount * TRANSFER


def sell_proceeds(price: float, shares: int) -> float:
    amount = price * shares
    return amount - max(MIN_COMMISSION, amount * COMMISSION) - amount * STAMP_DUTY - amount * TRANSFER


def run_variant(books: dict[str, pd.DataFrame], regime200: dict, regime20: dict,
                gate_open: dict | None, timing: bool | str, capital: float = 100_000.0) -> dict:
    """逐日盯市撮合。gate_open: {code: set(可买日期)}，None 表示不设门槛。"""
    dates = sorted({d for df in books.values() for d in df["date"].tolist()})
    idx_pos: dict[str, dict[str, int]] = {
        code: {d: i for i, d in enumerate(df["date"].tolist())} for code, df in books.items()
    }
    cash = capital
    positions: dict[str, dict] = {}
    equity_curve: list[tuple[str, float]] = []
    trades: list[dict] = []
    pending_exits: dict[str, dict] = {}
    pending_entries: list[dict] = []

    for day in dates:
        # 1) 开盘：先卖后买
        for code in list(pending_exits):
            pos = positions.pop(code, None)
            info = pending_exits.pop(code)
            if not pos:
                continue
            df = books[code]
            i = idx_pos[code].get(day)
            if i is None:
                cash += sell_proceeds(info["px"], pos["shares"])  # 停牌按最后估值
                continue
            px = float(df["open"].iloc[i]) * (1 - SLIPPAGE)
            cash += sell_proceeds(px, pos["shares"])
            ret = px / pos["entry_px"] - 1
            trades.append({"code": code, "name": pos["name"], "entry_date": pos["entry_date"],
                           "exit_date": day, "entry": round(pos["entry_px"], 3), "exit": round(px, 3),
                           "ret": round(ret, 5), "days": pos["days"], "reason": info["reason"]})

        equity_now = cash + sum(p["shares"] * p["last_px"] for p in positions.values())
        for sig in pending_entries:
            if len(positions) >= MAX_POS:
                break
            code = sig["code"]
            if code in positions:
                continue
            df = books[code]
            i = idx_pos[code].get(day)
            if i is None:
                continue
            px = float(df["open"].iloc[i]) * (1 + SLIPPAGE)
            budget = min(equity_now / MAX_POS, cash)
            shares = int(budget / px // 100) * 100
            if shares <= 0:
                continue
            cost = buy_cost(px, shares)
            if cost > cash:
                shares -= 100
                if shares <= 0:
                    continue
                cost = buy_cost(px, shares)
            cash -= cost
            positions[code] = {"name": sig["name"], "shares": shares, "entry_px": px,
                               "entry_date": day, "days": 0, "last_px": px}
        pending_entries = []

        # 2) 收盘：盯市 + 生成明日卖单 + 生成明日买单
        for code, pos in positions.items():
            df = books[code]
            i = idx_pos[code].get(day)
            if i is None:
                continue
            close = float(df["close"].iloc[i])
            pos["last_px"] = close
            pos["days"] += 1
            if code not in pending_exits:
                if close < float(df["ma20"].iloc[i]) and pos["days"] > 1:
                    pending_exits[code] = {"px": close, "reason": "破MA20"}
                elif pos["days"] >= HOLD_DAYS:
                    pending_exits[code] = {"px": close, "reason": "满20日"}

        equity_now = cash + sum(p["shares"] * p["last_px"] for p in positions.values())
        equity_curve.append((day, equity_now))

        for code, df in books.items():
            if code in positions:
                continue
            i = idx_pos[code].get(day)
            if i is None or i + 1 >= len(df):
                continue
            if not bool(df["signal"].iloc[i]):
                continue
            if timing == "ma200" and not bool(regime200.get(day, False)):
                continue
            if timing == "ma20" and not bool(regime20.get(day, False)):
                continue
            if gate_open is not None and day not in gate_open.get(code, set()):
                continue
            pending_entries.append({"code": code, "name": str(df["name"].iloc[0]) if "name" in df else code})

    # 统计
    eq = pd.Series([v for _, v in equity_curve], index=[d for d, _ in equity_curve])
    total = eq.iloc[-1] / capital - 1 if len(eq) else 0.0
    peak = eq.cummax()
    mdd = float((eq / peak - 1).min()) if len(eq) else 0.0
    years = max(len(eq) / 244, 1e-9)
    cagr = (1 + total) ** (1 / years) - 1 if total > -1 else -1.0
    daily = eq.pct_change().dropna()
    sharpe = float(daily.mean() / daily.std() * math.sqrt(244)) if len(daily) > 2 and daily.std() > 0 else 0.0
    t = pd.DataFrame(trades)
    wins = t[t["ret"] > 0] if len(t) else t
    losses = t[t["ret"] <= 0] if len(t) else t
    pf = (wins["ret"].sum() / abs(losses["ret"].sum())) if len(losses) and losses["ret"].sum() != 0 else (
        float("inf") if len(wins) else 0.0)
    return {
        "trades": int(len(t)),
        "win_rate": round(float(len(wins) / len(t)), 4) if len(t) else 0.0,
        "avg": round(float(t["ret"].mean()), 4) if len(t) else 0.0,
        "pf": round(float(pf), 2),
        "total_return": round(float(total), 4),
        "cagr": round(float(cagr), 4),
        "mdd": round(mdd, 4),
        "sharpe": round(sharpe, 2),
        "final_equity": round(float(eq.iloc[-1]), 0) if len(eq) else capital,
        "equity": [(d, round(float(v), 0)) for d, v in list(zip(eq.index, eq.values))[::5]],
        "trades_detail": trades[-40:],
    }


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="回测 v4：固定池 + 逐日盯市 + 费用滑点")
    ap.add_argument("--symbols", type=int, default=150, help="股票池大小（流通市值前 N）")
    ap.add_argument("--rebuild-pool", action="store_true", help="重建股票池缓存")
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--out", default="data/logs/backtest_v4.json")
    args = ap.parse_args()

    t0 = time.time()
    pool = load_pool(args.symbols, args.rebuild_pool)
    books: dict[str, pd.DataFrame] = {}
    gate_cache: dict[str, set[str]] = {}
    gate_l20: dict[str, set[str]] = {}
    for idx, item in enumerate(pool, 1):
        df = load_kline(item["code"])
        if df is None:
            continue
        df = with_signals(df)
        df["name"] = item["name"]
        books[item["code"]] = df
        if idx % 50 == 0:
            print(f"  …载入 {idx}/{len(pool)}")
    print(f"可用标的 {len(books)} 只，交易日 {len({d for df in books.values() for d in df['date']})} 个")

    print("预计算财务门槛（20/10 与 10/5）…")
    for code, df in books.items():
        hist = bf.fetch_history(code)
        if not hist:
            gate_cache[code] = set()
            gate_l20[code] = set()
            continue
        ok, ok_loose = set(), set()
        for d in df["date"].tolist():
            if bf.gate_ok(hist, d, 20.0, 10.0)[0]:
                ok.add(d)
            if bf.gate_ok(hist, d, 10.0, 5.0)[0]:
                ok_loose.add(d)
        gate_cache[code] = ok
        gate_l20[code] = ok_loose
    print(f"  有任一门槛可用的标的 {sum(1 for v in gate_cache.values() if v)}/{len(books)}")

    regime200 = index_regime(200)
    regime20 = index_regime(20)

    variants = [
        ("趋势 only（无门槛无择时）", None, False),
        ("趋势 + 门槛 20/10", gate_cache, False),
        ("趋势 + 门槛 10/5", gate_l20, False),
        ("趋势 + MA200 择时（现行）", None, "ma200"),
        ("趋势 + MA20 解锁（替代解锁）", None, "ma20"),
        ("趋势 + 20/10 + MA200 择时（生产配置）", gate_cache, "ma200"),
        ("趋势 + 20/10 + MA20 解锁", gate_cache, "ma20"),
    ]

    rows = []
    for label, gate, timing in variants:
        st = run_variant(books, regime200, regime20, gate, timing, args.capital)
        rows.append({"variant": label, **{k: v for k, v in st.items() if k not in ("equity", "trades_detail")}})
        print(f"  {label:34s} 成交 {st['trades']:3d}  胜率 {st['win_rate']*100:5.1f}%  "
              f"均值 {st['avg']*100:+.2f}%  PF {st['pf']:5.2f}  "
              f"总收益 {st['total_return']*100:+7.1f}%  年化 {st['cagr']*100:+6.1f}%  "
              f"回撤 {st['mdd']*100:6.1f}%  夏普 {st['sharpe']:.2f}")

    out = {
        "generated_at": datetime.now().isoformat(),
        "pool_size": len(books),
        "pool_rule": "流通市值前 N（缓存，含幸存者偏差）",
        "period": [min(d for df in books.values() for d in df["date"]),
                   max(d for df in books.values() for d in df["date"])],
        "costs": {"commission": COMMISSION, "min_commission": MIN_COMMISSION, "stamp_duty": STAMP_DUTY,
                  "transfer": TRANSFER, "slippage": SLIPPAGE, "max_pos": MAX_POS, "hold_days": HOLD_DAYS},
        "variants": rows,
    }
    path = ROOT / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n用时 {time.time() - t0:.0f}s，结果写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
