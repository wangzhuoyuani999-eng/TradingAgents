"""Live intraday check for the two open orders (run during the session)."""
import sys

import pandas as pd
import requests

FIELDS = "f43,f44,f45,f46,f47,f48,f57,f58,f60,f50,f168,f169,f170"

WATCH = [
    ("0.002415", "海康", "002415.SZ", 34.40),
    ("1.601166", "兴业", "601166.SS", 19.70),
    ("1.600036", "招行", "600036.SS", None),
    ("1.000001", "上证", None, None),
    ("0.399001", "深成", None, None),
    ("0.399006", "创业板", None, None),
]

SEGMENTS = [(9 * 60 + 30, 11 * 60 + 30), (13 * 60, 15 * 60)]

# Typical A-share cumulative volume profile: (minutes elapsed, fraction of day).
CURVE = [(0, 0.0), (30, 0.26), (60, 0.40), (120, 0.58), (180, 0.72), (240, 1.0)]


def minutes_elapsed(now: pd.Timestamp) -> int:
    total = 0
    for start, end in SEGMENTS:
        s = now.replace(hour=start // 60, minute=start % 60, second=0, microsecond=0)
        e = now.replace(hour=end // 60, minute=end % 60, second=0, microsecond=0)
        if now >= e:
            total += (e - s).total_seconds() / 60
        elif now > s:
            total += (now - s).total_seconds() / 60
    return int(total)


def expected_share(elapsed: int) -> float:
    exp = 0.0
    for (m0, f0), (m1, f1) in zip(CURVE, CURVE[1:]):
        if elapsed >= m1:
            exp = f1
        elif elapsed > m0:
            return f0 + (f1 - f0) * (elapsed - m0) / (m1 - m0)
        else:
            break
    return exp


def main() -> None:
    now = pd.Timestamp.now(tz="Asia/Shanghai")
    elapsed = minutes_elapsed(now)
    print(f"== {now:%H:%M:%S}  已交易 {elapsed} 分钟 ==")
    for secid, name, ticker, limit in WATCH:
        try:
            d = requests.get(
                "https://push2.eastmoney.com/api/qt/stock/get",
                params={"secid": secid, "fields": FIELDS},
                timeout=8,
            ).json().get("data") or {}
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: FAIL {exc}")
            continue
        if not d:
            print(f"{name}: no data")
            continue
        px = d["f43"] / 100
        amt = (d.get("f48") or 0) / 1e8
        low = d["f45"] / 100
        line = (f"{name:<4}{px:>8.2f} {d['f170']/100:>+6.2f}%  额{amt:>6.1f}亿 "
                f"量比{(d.get('f50') or 0)/100:>5.2f} 开{d['f46']/100:>7.2f} "
                f"高{d['f44']/100:>7.2f} 低{low:>7.2f}")
        if ticker:
            cache = pd.read_csv(f"data/cache/{ticker}-YFin-data.csv")
            avg_amt = (cache.Close * cache.Volume).tail(20).mean() / 1e8
            share = amt / avg_amt
            pace = share / expected_share(elapsed) if elapsed else 0
            line += f"  占日均{share*100:>5.1f}%  量能{pace:>4.2f}x"
            if limit is not None and low <= limit:
                line += "  ← 挂单已触及"
        print(line)
        if limit is not None:
            print(f"     挂单 {limit:.2f}：最低 {low:.2f}，"
                  f"{'已触及' if low <= limit else '未触及'}；现价距挂单 {(px / limit - 1) * 100:+.2f}%")


if __name__ == "__main__":
    sys.exit(main())
