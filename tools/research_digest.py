"""券商研报摘要（东财 reportapi）——把卖方观点纳入盘前消息面。

为什么加：`tools/news_digest.py` 只覆盖「外盘 + 7×24 快讯 + 公司公告」，
**没有券商研报**。而研报里有三样我们缺的东西：
  1. 评级（买入/增持/中性…）与评级变动；
  2. 目标价（部分研报有）；
  3. 卖方 EPS / PE 预测（今年 / 明年 / 后年）——比 F10 历史财务更前瞻。

用法（工作目录 = 仓库根）：
    .venv/Scripts/python.exe tools/research_digest.py                 # 持仓 + 候选池，近 30 天
    .venv/Scripts/python.exe tools/research_digest.py --days 90 --top 5
    .venv/Scripts/python.exe tools/research_digest.py --symbols 600885,000823

口径：只摘标题与字段事实（机构/日期/评级/目标价/EPS 预测），**不做观点复述、不替卖方背书**；
研报少或没有就写「近 N 天无研报」，不要用模型记忆补。
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "logs"
API = "https://reportapi.eastmoney.com/report/list"
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}


def portfolio_symbols() -> list[tuple[str, str]]:
    """从 PORTFOLIO.md 的「持仓与止损止盈」「候选池」两节取 (代码, 名称)。"""
    path = ROOT / "PORTFOLIO.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    out: list[tuple[str, str]] = []
    for heading in ("## 持仓与止损止盈", "## 候选池"):
        lines = text.splitlines()
        try:
            start = next(i for i, ln in enumerate(lines) if ln.startswith(heading))
        except StopIteration:
            continue
        for ln in lines[start + 1:]:
            if ln.startswith("## "):
                break
            if not ln.lstrip().startswith("|"):
                continue
            cells = [c.strip().replace("**", "") for c in ln.strip().strip("|").split("|")]
            if len(cells) < 2 or "标的" in cells[0]:
                continue
            m = re.search(r"\b(0\d{5}|3\d{5}|6\d{5})\b", cells[1])
            if not m:
                continue
            pair = (m.group(1), cells[0])
            if pair not in out:
                out.append(pair)
    return out


def fetch_reports(code: str, days: int, size: int = 30) -> list[dict]:
    end = datetime.now()
    begin = end - timedelta(days=days)
    params = {
        "industryCode": "*", "pageSize": size, "industry": "*", "rating": "*",
        "ratingChange": "*", "beginTime": begin.strftime("%Y-%m-%d"),
        "endTime": end.strftime("%Y-%m-%d"), "pageNo": 1, "qType": 0, "code": code,
    }
    try:
        data = requests.get(API, params=params, headers=UA, timeout=12).json()
    except Exception as exc:  # noqa: BLE001
        print(f"[!] {code} 研报拉取失败：{exc}", file=sys.stderr)
        return []
    return data.get("data") or []


def summarize(code: str, name: str, reports: list[dict], top: int) -> list[str]:
    if not reports:
        return [f"### {code} {name}", "", f"近 {days_global} 天无券商研报", ""]
    ratings = Counter((r.get("emRatingName") or r.get("sRatingName") or "未评级") for r in reports)
    aims = [float(r["indvAimPriceT"]) for r in reports if str(r.get("indvAimPriceT") or "").strip()]
    lines = [f"### {code} {name}（近 {days_global} 天 {len(reports)} 篇）", ""]
    lines.append("评级分布：" + "、".join(f"{k} {v} 篇" for k, v in ratings.most_common()))
    if aims:
        lines.append(f"目标价：{len(aims)} 篇给出，区间 {min(aims):.2f}–{max(aims):.2f}（均值 {sum(aims)/len(aims):.2f}）")
    else:
        lines.append("目标价：本期研报未给出")
    latest = reports[0]
    eps = latest.get("predictThisYearEps")
    eps2 = latest.get("predictNextYearEps")
    pe = latest.get("predictThisYearPe")
    if eps:
        lines.append(f"最新一篇的卖方预测：今年 EPS {eps}、明年 EPS {eps2 or '—'}、今年 PE {pe or '—'}")
    lines.append("")
    for r in reports[:top]:
        date = str(r.get("publishDate") or "")[:10]
        org = r.get("orgSName") or r.get("orgName") or "?"
        rating = r.get("emRatingName") or r.get("sRatingName") or "—"
        title = (r.get("title") or "").replace("\n", " ")[:60]
        lines.append(f"- {date}｜{org}｜{rating}｜{title}")
    lines.append("")
    return lines


days_global = 30


def main() -> int:
    global days_global
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="券商研报摘要")
    ap.add_argument("--days", type=int, default=30, help="回看天数（默认 30）")
    ap.add_argument("--top", type=int, default=3, help="每只最多列几篇（默认 3）")
    ap.add_argument("--symbols", default="", help="逗号分隔代码；默认取 PORTFOLIO.md 持仓+候选池")
    ap.add_argument("--out", default="", help="输出路径，默认 data/logs/research_<日期>.md")
    args = ap.parse_args()
    days_global = args.days

    if args.symbols:
        targets = [(s.strip(), s.strip()) for s in args.symbols.split(",") if s.strip()]
    else:
        targets = portfolio_symbols()
    if not targets:
        print("没有标的可查（PORTFOLIO.md 未给出代码，且未传 --symbols）", file=sys.stderr)
        return 2

    md = [f"# 券商研报摘要 {datetime.now():%Y-%m-%d %H:%M}", "",
          f"回看 {args.days} 天；标的 {len(targets)} 只；来源：东方财富研报中心（reportapi）", "",
          "> 只摘字段事实（机构/日期/评级/目标价/EPS 预测），不复述卖方观点、不替其背书。", ""]
    for code, name in targets:
        reports = fetch_reports(code, args.days)
        md += summarize(code, name, reports, args.top)

    out = Path(args.out) if args.out else OUT_DIR / f"research_{datetime.now():%Y%m%d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"写入 {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}（{out.stat().st_size} 字节）")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
