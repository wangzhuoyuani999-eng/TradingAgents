"""Screen main-board A-shares for the post-reduction watchlist.

Rules for a ~10k CNY book: a 100-share lot must be affordable, liquidity must be
real, and money must be flowing in rather than out. Prices, F10 reports and
capital flow all come from Eastmoney; nothing is estimated.
"""
from __future__ import annotations

import json

import requests

from tradingagents.dataflows.vendors.eastmoney.client import (
    f10_reports,
    is_cn_symbol,
    kline,
    money_flow,
)

H = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
CLIST = "https://push2.eastmoney.com/api/qt/clist/get"
FIELDS = "f2,f3,f5,f6,f8,f9,f10,f12,f14,f20,f21,f23,f62,f184"
# Shanghai + Shenzhen main boards only: 创业板/科创板 need permissions this
# 10k account does not have.
FS = "m:1+t:2,m:0+t:6"

PRICE_RANGE = (5.0, 45.0)
MIN_AMOUNT = 3e8
MIN_MCAP = 150e8
PE_RANGE = (0.0, 60.0)
MAX_TODAY_CHG = 6.0      # never screen in a limit-up we cannot buy
DEEP_DIVE = 36


def fetch_page(page: int, size: int = 100) -> list[dict]:
    resp = requests.get(
        CLIST,
        params={"pn": page, "pz": size, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                "fid": "f62", "fs": FS, "fields": FIELDS},
        headers=H, timeout=15,
    ).json()
    return (resp.get("data") or {}).get("diff") or []


def main() -> None:
    rows, seen = [], set()
    for page in range(1, 5):
        for r in fetch_page(page):
            if r.get("f12") not in seen:
                seen.add(r.get("f12"))
                rows.append(r)

    pool = []
    for r in rows:
        price, amount, mcap, pe = r.get("f2"), r.get("f6") or 0, r.get("f20") or 0, r.get("f9")
        name = r.get("f14") or ""
        if not price or not (PRICE_RANGE[0] <= price <= PRICE_RANGE[1]):
            continue
        if amount < MIN_AMOUNT or mcap < MIN_MCAP:
            continue
        if pe is None or not (PE_RANGE[0] < pe < PE_RANGE[1]):
            continue
        if "ST" in name or "退" in name:
            continue
        if not (-3.0 <= (r.get("f3") or 0) <= MAX_TODAY_CHG):
            continue
        pool.append({"code": r["f12"], "name": name, "price": price, "chg": r.get("f3"),
                     "amount_yi": amount / 1e8, "mcap_yi": mcap / 1e8, "pe": pe,
                     "pb": r.get("f23"), "main_net_yi": (r.get("f62") or 0) / 1e8,
                     "main_pct": r.get("f184") or 0})

    print(f"池子 {len(rows)} 只 → 价格/流动性/市值/PE/今日涨幅 过滤后 {len(pool)} 只")
    pool.sort(key=lambda c: c["main_pct"], reverse=True)

    idx = kline("000001.SS", "20260901", "20261231")
    idx20 = (idx[-1]["close"] / idx[-21]["close"] - 1) * 100

    out = []
    for c in pool[:DEEP_DIVE]:
        symbol = f"{c['code']}.{'SS' if c['code'].startswith('6') else 'SZ'}"
        if not is_cn_symbol(symbol):
            continue
        bars = kline(symbol, "20260801", "20261231")
        if len(bars) < 25:
            continue
        r20 = (bars[-1]["close"] / bars[-21]["close"] - 1) * 100
        flows = money_flow(symbol, 5)
        flow5 = sum(f["main_net"] for f in flows) / 1e8
        report = (f10_reports(symbol, 1) or [{}])[0]
        out.append({
            **c, "symbol": symbol, "r20": r20, "rs20": r20 - idx20, "flow5_yi": flow5,
            "rev_yoy": report.get("TOTALOPERATEREVETZ"),
            "np_yoy": report.get("PARENTNETPROFITTZ"),
            "roe": report.get("ROEJQ"), "report": report.get("REPORT_DATE_NAME"),
        })

    # Trend + money must both be on side; the relative-strength term keeps names
    # that merely bounced today from topping the list.
    out = [o for o in out if o["r20"] > -2.0 and o["flow5_yi"] > 0]
    for o in out:
        o["score"] = o["rs20"] * 0.4 + o["main_pct"] * 0.6 + o["flow5_yi"] * 0.8
    out.sort(key=lambda o: o["score"], reverse=True)

    print(f"通过趋势/资金条件 {len(out)} 只（上证 20 日 {idx20:+.2f}%）\n")
    print(f"{'代码':<8}{'名称':<10}{'价':>7}{'一手':>7}{'今涨':>7}{'20日':>7}{'超额':>7}"
          f"{'5日主力':>9}{'占比':>6}{'PE':>6}{'营收YoY':>8}{'净利YoY':>8}")
    for o in out[:10]:
        print(f"{o['code']:<8}{o['name']:<10}{o['price']:>7.2f}{o['price']*100:>7.0f}"
              f"{o['chg']:>6.1f}%{o['r20']:>6.1f}%{o['rs20']:>6.1f}%{o['flow5_yi']:>8.2f}亿"
              f"{o['main_pct']:>5.1f}%{o['pe']:>6.1f}"
              f"{(o['rev_yoy'] or 0):>7.1f}%{(o['np_yoy'] or 0):>7.1f}%")

    json.dump({"index_rs20": idx20, "candidates": out[:12]},
              open("data/watchlist_raw.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
