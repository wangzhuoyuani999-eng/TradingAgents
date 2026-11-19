"""选股 v3 —— 按 research/选股策略_v1.md 的四层漏斗实现。

第 0 层（生存过滤）→ 第 1 层（趋势模板）→ 第 2 层（基本面）→ 第 3 层（资金）

用法：
    python screen_v3.py                # 全流程，输出前 20
    python screen_v3.py --stage1-only  # 只跑到趋势层（快）

输出：控制台表格 + data/logs/screen_v3_<日期>.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd

import data_sources as ds

F10 = "https://datacenter.eastmoney.com/securities/api/data/v1/get"

PRICE_MIN, PRICE_MAX = 3.0, 60.0
AMOUNT_MIN = 1e8  # 20 日均额 1 亿


def fetch_universe() -> pd.DataFrame:
    """全 A 股列表（新浪，直连，不依赖代理）。"""
    df = ds.universe()
    if df.empty:
        return df
    df = df.rename(columns={"nmc": "floatcap"})
    # 新浪的 mktcap / nmc 单位是「万元」，统一换成元
    for col in ("mktcap", "floatcap"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce") * 1e4
    for col in ["price", "pct", "amount", "pe", "floatcap", "mktcap", "pb"]:
        if col not in df.columns:
            df[col] = float("nan")
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def stage0(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d = d[~d["name"].astype(str).str.contains("ST|退", na=False)]
    d = d[d["price"].between(PRICE_MIN, PRICE_MAX)]
    d = d[d["amount"].fillna(0) >= 3e7]          # 当日成交额 ≥ 3000 万（后续用 20 日均额再筛）
    d = d[d["floatcap"].fillna(0) >= 3e9]        # 流通市值 ≥ 30 亿
    # 账户约束（必须先过滤）：
    #   - 科创板 688/689：买不了
    #   - 创业板 300/301：买不了（无权限）
    #   - 北交所 4/8 开头、B 股 9 开头：不做
    bad = ("688", "689", "300", "301", "8", "4", "9")
    d = d[~d["code"].astype(str).str.startswith(bad)]
    assert not d["code"].astype(str).str.startswith(("688", "689", "300", "301")).any(), "板块过滤失效！"
    return d


def kline(code: str, limit: int = 320) -> pd.DataFrame | None:
    """前复权日线 + 用实时行情修补缺失的当日 K 线。

    腾讯/新浪的日线在收盘后一段时间内仍停留在前一交易日，
    会把「今天刚创出的新高」漏掉；这里用实时价补一根当日 bar。
    """
    k = ds.kline_qfq(code, limit)
    if k is None:
        return None
    k = k.copy()
    if "amount" not in k.columns:
        k["amount"] = k["volume"] * k["close"]

    # 补当日 bar：日线最后一天 < 今天，且能拿到实时价/高低。
    # 只在盘中补——盘前/盘后 quote() 返回的是上一交易日收盘价，补进去等于重复一根 bar，
    # 会把 MA20 和趋势分算歪。
    try:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        in_session = (now.hour * 60 + now.minute) >= (9 * 60 + 35) and now.hour < 15
        q = ds.quote([code]).get(code) if in_session else None
        last = str(k["date"].iloc[-1])[:10]
        if q and last < today and q["px"] > 0:
            bar = pd.DataFrame([{
                "date": today, "open": q["px"], "close": q["px"],
                "high": max(q["high"], q["px"]), "low": min(q["low"], q["px"]),
                "volume": float("nan"),
            }])
            bar["amount"] = bar["volume"] * bar["close"]
            k = pd.concat([k, bar], ignore_index=True)
    except Exception:
        pass
    return k[["date", "open", "close", "high", "low", "volume", "amount"]].reset_index(drop=True)


def trend_score(k: pd.DataFrame) -> dict | None:
    c = k["close"]
    if len(c) < 200:
        return None
    ma50 = c.tail(50).mean()
    ma150 = c.tail(150).mean()
    ma200 = c.tail(200).mean()
    ma200_prev = c.iloc[-220:-20].tail(200).mean() if len(c) >= 220 else c.tail(200).mean()
    last = c.iloc[-1]
    low52 = k["low"].tail(250).min()
    high52 = k["high"].tail(250).max()

    checks = {
        "price>ma150&ma200": last > ma150 and last > ma200,
        "ma150>ma200": ma150 > ma200,
        "ma200_rising": ma200 > ma200_prev,
        "ma50>ma150>ma200": ma50 > ma150 > ma200,
        "price>ma50": last > ma50,
        "above_low_30%": last / low52 - 1 >= 0.30,
        "near_high_25%": last / high52 - 1 >= -0.25,
        "no_crash_20d": not (k["close"].pct_change().tail(20) < -0.08).any(),
    }
    score = sum(4 for v in checks.values() if v)
    ret120 = last / c.iloc[-120] - 1 if len(c) >= 120 else 0.0
    return {
        "checks": checks, "trend_score": score, "ret120": ret120,
        "ma20": c.tail(20).mean(), "ma50": ma50, "ma200": ma200,
        "low52": low52, "high52": high52, "last": last,
        "vol20": k["volume"].tail(20).mean(), "amt20": k["amount"].tail(20).mean(),
        "high60": k["high"].tail(60).max(),
        "low20": k["low"].tail(20).min(),
    }


def f10_growth(code: str) -> dict:
    """最近一期净利/营收同比、ROE、毛利率（东财，需要代理；失败就返回空，跳过基本面门槛）。

    高频调用会被限流（返回空），所以这里带 3 次重试 + 退避。
    """
    import time as _t
    import requests as _rq

    sec = f'{code}.SH' if code.startswith("6") else f'{code}.SZ'
    for attempt in range(3):
        try:
            r = _rq.get(F10, params={
                "reportName": "RPT_F10_FINANCE_MAINFINADATA", "columns": "ALL",
                "filter": f'(SECUCODE="{sec}")',
                "pageNumber": 1, "pageSize": 1, "sortColumns": "REPORT_DATE", "sortTypes": -1,
            }, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).json()
            row = ((r.get("result") or {}).get("data") or [{}])[0]
            if row.get("PARENTNETPROFITTZ") is not None:
                _t.sleep(0.25)
                return {
                    "yoy_net": row.get("PARENTNETPROFITTZ"),
                    "yoy_rev": row.get("TOTALOPERATEREVETZ"),
                    "roe": row.get("ROEJQ"),
                    "gross": row.get("XSMLL"),
                    "report": row.get("REPORT_DATE"),
                }
        except Exception:
            pass
        _t.sleep(0.8 * (attempt + 1))
    return {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage1-only", action="store_true")
    ap.add_argument("--limit", type=int, default=160, help="进入 K 线计算的股票数上限")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    t0 = time.time()
    print("拉取全市场行情…")
    uni = fetch_universe()
    print(f"  全市场 {len(uni)} 只")
    s0 = stage0(uni)
    print(f"  第0层生存过滤后 {len(s0)} 只")

    # 按成交额排序取前 N 做 K 线分析（成交额大的先看，兼顾流动性）
    cand = s0.sort_values("amount", ascending=False).head(args.limit)
    print(f"计算趋势模板（{len(cand)} 只）…")
    recs = []
    for i, row in enumerate(cand.itertuples(), 1):
        k = kline(row.code)
        if k is None:
            continue
        t = trend_score(k)
        if t is None:
            continue
        if t["amt20"] < AMOUNT_MIN:
            continue
        recs.append({
            "code": row.code, "name": row.name, "price": float(row.price),
            "pct": float(row.pct) if pd.notna(row.pct) else None,
            "pe_ttm": float(row.pe) if pd.notna(row.pe) else None,
            "pb": float(row.pb) if pd.notna(row.pb) else None,
            "mktcap_yi": round(float(row.mktcap) / 1e8, 1) if pd.notna(row.mktcap) else None,
            "main_net_wan": None,
            **{k2: t[k2] for k2 in ["trend_score", "ret120", "ma20", "ma50", "ma200",
                                    "low52", "high52", "last", "vol20", "amt20", "high60", "low20"]},
            "checks": t["checks"],
        })
        if i % 20 == 0:
            print(f"  …{i}/{len(cand)}")

    if not recs:
        print("没有任何股票通过趋势层。")
        return

    df = pd.DataFrame(recs)
    # 相对强度分位
    df["rs_pct"] = df["ret120"].rank(pct=True)
    df["rs_score"] = (df["rs_pct"] * 20).round(1)
    df["trend_pts"] = df["trend_score"]  # 0-32 → 上限 30
    df["score"] = df["trend_pts"] + df["rs_score"]

    df["满分8条"] = df["trend_score"] >= 32
    passed = df[df["trend_score"] >= 28].copy()   # 7/8 以上进池，8/8 优先
    print(f"  趋势模板 8/8 共 {(df['trend_score'] >= 32).sum()} 只；7/8 以上 {len(passed)} 只")

    if args.stage1_only:
        out = passed.sort_values("score", ascending=False).head(args.top)
        print(out[["code", "name", "price", "ret120", "trend_score", "score"]].to_string(index=False))
        return

    print(f"拉取基本面（{min(len(passed), 40)} 只）…")
    for row in passed.head(40).itertuples():
        g = f10_growth(row.code)
        passed.loc[passed["code"] == row.code, "yoy_net"] = g.get("yoy_net")
        passed.loc[passed["code"] == row.code, "yoy_rev"] = g.get("yoy_rev")
        passed.loc[passed["code"] == row.code, "roe"] = g.get("roe")
        passed.loc[passed["code"] == row.code, "gross"] = g.get("gross")

    for col in ["yoy_net", "yoy_rev", "roe", "gross"]:
        if col not in passed.columns:
            passed[col] = np.nan
        passed[col] = pd.to_numeric(passed[col], errors="coerce")

    # 硬门槛（CANSLIM 的 C 与 A）：季净利同比 ≥ +20%，营收同比 ≥ +10%
    # 缺数据的**不放行**（否则限流会把不合格的票带进来），但单独列出来供人工复核。
    before = len(passed)
    has_data = passed["yoy_net"].notna()
    gate = passed[
        has_data
        & (passed["yoy_net"] >= 20)
        & (passed["yoy_rev"] >= 10)
    ].copy()
    missing = passed[~has_data]
    print(f"  基本面硬门槛（净利≥+20%、营收≥+10%）后 {len(gate)}/{before} 只"
          f"（另 {len(missing)} 只无财务数据，已剔除）")
    passed = gate

    rows = []
    for r in passed.itertuples():
        f_score = 0.0
        if pd.notna(r.yoy_net):
            f_score += min(max(r.yoy_net, 0) / 20 * 8, 8)
        if pd.notna(r.yoy_rev):
            f_score += min(max(r.yoy_rev, 0) / 10 * 4, 4)
        if pd.notna(r.roe):
            f_score += min(max(r.roe, 0) / 12 * 4, 4)
        if pd.notna(r.gross):
            f_score += min(max(r.gross, 0) / 40 * 4, 4)
        # 资金 15 分：今日主力净流入 + 成交额
        fund = 0.0
        if pd.notna(r.main_net_wan):
            fund += 7 if r.main_net_wan > 0 else 0
        fund += 5 if r.amt20 > 3e8 else 3
        liq = 3 if r.amt20 < 3e8 else 5
        rows.append({
            "code": r.code, "name": r.name, "price": round(r.last, 2),
            "pct": r.pct, "趋势分": r.trend_score, "RS分": r.rs_score,
            "基本面分": round(f_score, 1), "资金分": fund, "流动分": liq,
            "总分": round(r.trend_score + r.rs_score + f_score + fund + liq, 1),
            "净利同比": r.yoy_net, "营收同比": r.yoy_rev, "ROE": r.roe, "毛利率": r.gross,
            "6月涨幅%": round(r.ret120 * 100, 1),
            "距52周高%": round((r.last / r.high52 - 1) * 100, 1),
            "日均额亿": round(r.amt20 / 1e8, 2),
            "买点参考_突破": round(r.high60, 2),
            "止损_MA20": round(r.ma20, 2),
        })

    if not rows:
        print("没有股票同时通过趋势与基本面层。")
        best = passed.sort_values("score", ascending=False).head(10)
        print(best[["code", "name", "price", "trend_score", "ret120"]].to_string(index=False))
        return

    out = pd.DataFrame(rows).sort_values("总分", ascending=False)
    print()
    print(out.head(args.top)[["code", "name", "price", "趋势分", "RS分", "基本面分", "总分",
                              "6月涨幅%", "净利同比", "日均额亿"]].to_string(index=False))

    os.makedirs("data/logs", exist_ok=True)
    path = f"data/logs/screen_v3_{datetime.now():%Y%m%d}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out.head(40).to_dict(orient="records"), fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n用时 {time.time() - t0:.0f}s，结果写入 {path}")


if __name__ == "__main__":
    sys.exit(main())
