"""Sector-driven screen: money went to semis / power equipment / media today."""
from __future__ import annotations

import json

import requests

from tradingagents.dataflows.vendors.eastmoney.client import (
    f10_reports,
    kline,
    money_flow,
)

H = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
CLIST = "https://push2.eastmoney.com/api/qt/clist/get"

SECTORS = ["半导体", "光伏设备", "电力设备", "传媒", "电池"]
FIELDS = "f2,f3,f6,f9,f12,f14,f20,f62,f184"
MAIN_BOARD = ("600", "601", "603", "605", "000", "001", "002")


def board_codes() -> dict[str, str]:
    r = requests.get(CLIST, params={"pn": 1, "pz": 200, "po": 1, "np": 1, "fltt": 2,
                                    "invt": 2, "fid": "f62", "fs": "m:90+t:2",
                                    "fields": "f12,f14"}, headers=H, timeout=12).json()
    return {d["f14"]: d["f12"] for d in (r.get("data") or {}).get("diff") or []}


def constituents(code: str, limit: int = 60) -> list[dict]:
    r = requests.get(CLIST, params={"pn": 1, "pz": limit, "po": 1, "np": 1, "fltt": 2,
                                    "invt": 2, "fid": "f62", "fs": f"b:{code}",
                                    "fields": FIELDS}, headers=H, timeout=12).json()
    return (r.get("data") or {}).get("diff") or []


def main() -> None:
    boards = board_codes()
    pool, seen = [], set()
    for name in SECTORS:
        code = boards.get(name)
        if not code:
            print(f"! no board code for {name}")
            continue
        for r in constituents(code):
            c = r.get("f12") or ""
            if c in seen or not c.startswith(MAIN_BOARD):
                continue
            seen.add(c)
            def num(v, default=None):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return default
            price, amt, pe = num(r.get("f2")), num(r.get("f6"), 0.0), num(r.get("f9"))
            if price is None or not (5 <= price <= 45) or amt < 2e8:
                continue
            if pe is None or not (0 < pe < 80):
                continue
            chg = num(r.get("f3"), 0.0)
            if not (-2 <= chg <= 7):
                continue
            pool.append({"code": c, "name": r["f14"], "price": price, "chg": chg,
                         "amount_yi": amt / 1e8, "pe": pe,
                         "mcap_yi": (r.get("f20") or 0) / 1e8,
                         "main_yi": (r.get("f62") or 0) / 1e8,
                         "main_pct": r.get("f184") or 0, "sector": name})

    print(f"五个板块内符合价格/流动性/PE 条件的 {len(pool)} 只")
    pool.sort(key=lambda x: x["main_pct"], reverse=True)

    idx = kline("000001.SS", "20260901", "20261231")
    idx20 = (idx[-1]["close"] / idx[-21]["close"] - 1) * 100

    out = []
    for c in pool[:20]:
        sym = f"{c['code']}.{'SS' if c['code'].startswith('6') else 'SZ'}"
        bars = kline(sym, "20260801", "20261231")
        if len(bars) < 25:
            continue
        r20 = (bars[-1]["close"] / bars[-21]["close"] - 1) * 100
        flow5 = sum(f["main_net"] for f in money_flow(sym, 5)) / 1e8
        rep = (f10_reports(sym, 1) or [{}])[0]
        out.append({**c, "r20": r20, "rs20": r20 - idx20, "flow5": flow5,
                    "rev": rep.get("TOTALOPERATEREVETZ"), "np": rep.get("PARENTNETPROFITTZ")})

    out.sort(key=lambda x: x["rs20"] * 0.5 + x["main_pct"] * 0.5 + x["flow5"] * 0.6, reverse=True)
    print(f"\n{'代码':<8}{'名称':<8}{'板块':<6}{'价':>7}{'今涨':>7}{'20日超额':>9}"
          f"{'5日主力':>9}{'今占比':>7}{'PE':>6}{'净利YoY':>9}")
    for o in out[:10]:
        print(f"{o['code']:<8}{o['name']:<8}{o['sector']:<6}{o['price']:>7.2f}{o['chg']:>6.1f}%"
              f"{o['rs20']:>8.1f}%{o['flow5']:>8.2f}亿{o['main_pct']:>6.1f}%{o['pe']:>6.1f}"
              f"{(o['np'] or 0):>8.1f}%")
    json.dump({"idx20": idx20, "cands": out[:10]}, open("data/sector_cands.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
