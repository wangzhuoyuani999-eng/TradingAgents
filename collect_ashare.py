"""Collect the A-share batch results into one table."""
import json
import re
from pathlib import Path

REPORTS = Path("data/logs/reports")
NAMES = {
    "600519.SS": "贵州茅台", "000858.SZ": "五粮液", "300750.SZ": "宁德时代",
    "002594.SZ": "比亚迪", "601318.SS": "中国平安", "600036.SS": "招商银行",
    "601899.SS": "紫金矿业", "688981.SS": "中芯国际", "002415.SZ": "海康威视",
    "600276.SS": "恒瑞医药",
}

latest = {}
for d in REPORTS.iterdir():
    m = re.match(r"^(\d{6}\.(?:SS|SZ))_(\d{8}_\d{6})$", d.name)
    if not m or not d.is_dir():
        continue
    ticker, stamp = m.groups()
    if ticker not in NAMES:
        continue
    if ticker not in latest or stamp > latest[ticker][0]:
        latest[ticker] = (stamp, d)


def field(text, name):
    m = re.search(rf"\*\*{name}\*\*:\s*(.+)", text)
    return m.group(1).strip() if m else ""


rows = []
for ticker, (stamp, d) in sorted(latest.items()):
    dec = (d / "5_portfolio" / "decision.md").read_text(encoding="utf-8")
    trader = (d / "3_trading" / "trader.md").read_text(encoding="utf-8")
    summary = field(dec, "Executive Summary").replace("**", "")
    rows.append({
        "ticker": ticker,
        "name": NAMES[ticker],
        "rating": field(dec, "Rating"),
        "action": field(trader, "Action"),
        "target": field(dec, "Price Target"),
        "horizon": field(dec, "Time Horizon"),
        "stop": field(trader, "Stop Loss"),
        "summary": summary,
        "dir": str(d),
    })

print(json.dumps(rows, ensure_ascii=False, indent=1)[:200])
json.dump(rows, open("data/ashare_batch.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"\n{'代码':<11}{'名称':<10}{'交易员':<9}{'最终':<12}{'目标':<9}{'止损'}")
for r in sorted(rows, key=lambda x: (x["rating"] != "Overweight", x["ticker"])):
    print(f"{r['ticker']:<11}{r['name']:<10}{r['action']:<9}{r['rating']:<12}{r['target']:<9}{r['stop']}")
