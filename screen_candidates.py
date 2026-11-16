"""Quick quote/fundamental snapshot for a shortlist of A-share candidates."""
import json
import sys

import requests

SYMBOLS = [
    ("1.600030", "中信证券"), ("1.601166", "兴业银行"), ("0.000001", "平安银行"),
    ("1.601988", "中国银行"), ("1.600028", "中国石化"), ("1.601899", "紫金矿业"),
    ("0.002415", "海康威视"), ("1.601390", "中国中铁"), ("1.600050", "中国联通"),
    ("0.000725", "京东方A"), ("0.002027", "分众传媒"), ("1.601668", "中国建筑"),
    ("1.600016", "民生银行"), ("1.601818", "光大银行"), ("1.600000", "浦发银行"),
    ("1.601288", "农业银行"), ("1.601398", "工商银行"), ("0.002594", "比亚迪"),
    ("1.600276", "恒瑞医药"), ("1.600036", "招商银行"),
]

FIELDS = "f43,f44,f45,f46,f47,f48,f57,f58,f60,f162,f167,f116,f117,f168,f169,f170"


def quote(secid):
    r = requests.get(
        "https://push2.eastmoney.com/api/qt/stock/get",
        params={"secid": secid, "fields": FIELDS},
        timeout=10,
    )
    return r.json().get("data") or {}


def main():
    rows = []
    for secid, name in SYMBOLS:
        try:
            d = quote(secid)
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: FAIL {exc}", file=sys.stderr)
            continue
        if not d:
            continue
        rows.append({
            "code": d.get("f57"),
            "name": d.get("f58") or name,
            "price": d.get("f43", 0) / 100,
            "chg": d.get("f170", 0) / 100,
            "amount_yi": d.get("f48", 0) / 1e8,
            "pe": d.get("f162", 0) if isinstance(d.get("f162"), (int, float)) else None,
            "pb": d.get("f167", 0) if isinstance(d.get("f167"), (int, float)) else None,
            "mcap_yi": (d.get("f116") or 0) / 1e8,
            "turnover": d.get("f168", 0) / 100 if isinstance(d.get("f168"), (int, float)) else None,
        })
    rows.sort(key=lambda r: r["price"])
    for r in rows:
        lot = r["price"] * 100
        print(
            f"{r['code']:<8}{r['name']:<8}价{r['price']:>7.2f} 涨{r['chg']:>6.2f}% "
            f"额{r['amount_yi']:>7.1f}亿 PE{r['pe'] if r['pe'] else 0:>7.2f} "
            f"PB{r['pb'] if r['pb'] else 0:>6.2f} 市值{r['mcap_yi']:>7.0f}亿 一手{lot:>7.0f}元"
        )
    json.dump(rows, open("data/candidates.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
