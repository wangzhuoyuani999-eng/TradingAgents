"""盘前消息面摘要（隔夜外盘 + 宏观快讯 + 持仓/候选个股新闻与公告）。

为什么要有这个脚本（2026-11-25 定的）：
07:00 盘前尽调每次都要消息面，但之前是 agent 现场写临时脚本（`_tmp_news.py` 之类），
既不可追溯、也容易漏项。这里固化成一个可复跑的来源，输出 `data/logs/news_<YYYYMMDD>.md`。

数据来源（都是直连，不走代理）：
- 隔夜外盘/恒指/A50 期货：新浪 `hq.sinajs.cn`
- 宏观 7×24 快讯：东财 `fast_news`（与 diligence 的 news 分析师同源）
- 个股公告：东财 `announcements`；个股新闻：东财 `search_news`

用法（工作目录 = 仓库根）：

    .venv/Scripts/python.exe tools/news_digest.py                 # 持仓 + 候选池，自动取
    .venv/Scripts/python.exe tools/news_digest.py --size 400 --top 12
    .venv/Scripts/python.exe tools/news_digest.py --symbols 002415,600428

检索不到就明确写「未检索到」，**不要用模型记忆补**——这是 AGENTS.md 的硬要求。
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 本机系统代理偶尔是坏掉的，东财/新浪这几个域名必须直连
for _host in ("eastmoney.com", "push2.eastmoney.com", "sina.com.cn", "hq.sinajs.cn", "qt.gtimg.cn"):
    cur = __import__("os").environ.get("NO_PROXY", "")
    if _host not in cur:
        __import__("os").environ["NO_PROXY"] = (cur + "," + _host).strip(",")

from tradingagents.dataflows.vendors.eastmoney import news as en  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}

# 新浪行情代码 -> (展示名, 解析方式)
OVERSEAS = [
    ("gb_$dji", "道琼斯"),
    ("gb_$ixic", "纳斯达克"),
    ("gb_$ndx", "纳斯达克100"),
    ("gb_$inx", "标普500"),
    ("gb_$sox", "费城半导体(SOX)"),
    ("int_hangseng", "恒生指数"),
    ("hf_CHA50CFD", "富时A50期货"),
]

KEYWORDS = (
    "沪指|上证|深成|深证|创业板|A股|两市|北向|南向|融资|暴跌|大跌|重挫|跌停|涨停|利空|利好|"
    "关税|美联储|降息|加息|PCE|CPI|GDP|非农|费半|费城|半导体|芯片|算力|AI|MLF|逆回购|降准|"
    "证监会|央行|发改委|财政部|回购|分红|退市|监管"
)
KEYWORD_RE = re.compile(KEYWORDS)

OVERSEAS_LINE = re.compile(r'var hq_str_([\w$]+)="(.*)";')


def parse_sina(text: str) -> list[tuple[str, str, str]]:
    """解析新浪外盘行情，返回 [(展示名, 最新价, 涨跌幅)]。三种字段布局分别处理。"""
    wanted = dict(OVERSEAS)
    out: list[tuple[str, str, str]] = []
    for raw in text.strip().split("\n"):
        m = OVERSEAS_LINE.search(raw.strip())
        if not m:
            continue
        code, body = m.group(1), m.group(2)
        label = wanted.get(code)
        if not label or not body:
            continue
        parts = body.split(",")
        try:
            if code.startswith("gb_"):          # [1] 最新价 [2] 涨跌幅
                out.append((label, f"{float(parts[1]):,.2f}", f"{float(parts[2]):+.2f}%"))
            elif code.startswith("int_"):       # [0] 名称 [1] 最新价 [2] 涨跌额 [3] 涨跌幅
                out.append((label, f"{float(parts[1]):,.2f}", f"{float(parts[3]):+.2f}%"))
            else:                               # hf_* 期货： [0] 最新价 [7] 昨收 [13] 名称
                price = float(parts[0])
                prev = float(parts[7]) if len(parts) > 7 and parts[7] else 0.0
                pct = f"{(price / prev - 1) * 100:+.2f}%" if prev else "—"
                out.append((label, f"{price:,.2f}", pct))
        except (IndexError, ValueError):
            continue
    return out


def fetch_overseas() -> list[tuple[str, str, str]]:
    try:
        resp = requests.get("https://hq.sinajs.cn/list=" + ",".join(c for c, _ in OVERSEAS),
                            headers=UA, timeout=10)
        resp.encoding = "gbk"
        return parse_sina(resp.text)
    except Exception as exc:  # noqa: BLE001
        print(f"[!] 新浪外盘拉取失败：{exc}", file=sys.stderr)
        return []


def fetch_fast_news(size: int) -> list[dict]:
    try:
        return en.fast_news(size)
    except Exception as exc:  # noqa: BLE001
        print(f"[!] 东财快讯拉取失败：{exc}", file=sys.stderr)
        return []


def pick_macro(items: list[dict], top: int) -> list[str]:
    picked: list[str] = []
    seen: set[str] = set()
    for it in items:
        title = (it.get("title") or it.get("summary") or "").strip().replace("\n", " ")
        if not title or title in seen:
            continue
        seen.add(title)
        if KEYWORD_RE.search(title):
            when = (it.get("showTime") or "")[:16]
            picked.append(f"{when}　{title[:150]}")
        if len(picked) >= top:
            break
    return picked


def pick_symbol_news(items: list[dict], symbol: str, name: str, limit: int = 4) -> list[str]:
    """从 7×24 快讯里捞与该标的相关的条目：命中 stockList（0.002415 形式）或标题含名称。"""
    hits: list[str] = []
    codes = {f"0.{symbol}", f"1.{symbol}"}
    for it in items:
        title = (it.get("title") or it.get("summary") or "").strip().replace("\n", " ")
        if not title:
            continue
        stocks = set(it.get("stockList") or [])
        if not (stocks & codes or (name and name in title)):
            continue
        when = (it.get("showTime") or "")[:16]
        hits.append(f"快讯 {when}　{title[:120]}")
        if len(hits) >= limit:
            break
    return hits


def portfolio_symbols() -> list[tuple[str, str]]:
    """从 PORTFOLIO.md 的「持仓与止损止盈」「候选池」两节里取 (代码, 名称)。"""
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
            if len(cells) < 2:
                continue
            name, code = cells[0], cells[1]
            m = re.search(r"\b(0\d{5}|3\d{5}|6\d{5})\b", code)
            if not m or not name or "标的" in name:
                continue
            pair = (m.group(1), name)
            if pair not in out:
                out.append(pair)
    return out


def fetch_symbol_news(symbol: str, name: str, items: list[dict]) -> list[str]:
    lines: list[str] = []
    try:
        for it in en.announcements(symbol, 5):
            title = (it.get("title_ch") or it.get("title") or "").strip()
            when = (it.get("notice_date") or it.get("sort_date") or "")[:10]
            if title:
                lines.append(f"公告 {when}　{title[:110]}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"（公告拉取失败：{exc}）")
    lines += pick_symbol_news(items, symbol, name, 4)
    if not lines:
        lines.append("未检索到公司级新闻/公告（近 400 条快讯 + 公告接口均无命中）")
    return lines


def build(args) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    overseas = fetch_overseas()
    items = fetch_fast_news(args.size)
    macro = pick_macro(items, args.top)
    if args.symbols:
        targets = [(s.strip(), s.strip()) for s in args.symbols.split(",") if s.strip()]
    else:
        targets = portfolio_symbols()

    md: list[str] = [f"# 盘前消息面摘要 {stamp}", ""]

    md += ["## 一、隔夜外盘（新浪直连）", ""]
    if overseas:
        md += ["| 指标 | 最新 | 涨跌 |", "|---|---|---|"]
        md += [f"| {label} | {price} | {pct or '—'} |" for label, price, pct in overseas]
    else:
        md += ["未检索到（新浪外盘接口失败）"]

    md += ["", f"## 二、宏观/市场快讯（东财 7×24，按关键词过滤，取最近 {args.top} 条）", ""]
    if macro:
        md += [f"{i}. {item}" for i, item in enumerate(macro, 1)]
    else:
        md += ["未检索到关键快讯"]

    md += ["", "## 三、个股新闻与公告", ""]
    if not targets:
        md += ["未检索到持仓/候选标的（PORTFOLIO.md 里没有可用代码）"]
    for symbol, name in targets:
        md += [f"### {symbol} {name}", ""]
        rows = fetch_symbol_news(symbol, name, items)
        md += rows + [""]

    md += ["---", "",
           "口径：以上均为接口返回的原始标题与时间戳，**不做因果推断、不补模型记忆**；",
           "检索不到就写「未检索到」。要形成判断请结合技术面与基本面。", ""]

    out = Path(args.out) if args.out else ROOT / "data" / "logs" / f"news_{datetime.now():%Y%m%d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    return out


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="盘前消息面摘要")
    ap.add_argument("--size", type=int, default=400, help="拉多少条 7×24 快讯做过滤（默认 400）")
    ap.add_argument("--top", type=int, default=12, help="宏观快讯最多保留几条（默认 12）")
    ap.add_argument("--symbols", default="", help="逗号分隔代码，如 002415,600428；默认从 PORTFOLIO.md 取")
    ap.add_argument("--out", default="", help="输出路径，默认 data/logs/news_<日期>.md")
    args = ap.parse_args()

    out = build(args)
    print(f"写入 {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}（{out.stat().st_size} 字节）")
    print(out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
