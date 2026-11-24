"""生成静态交易台面板 `trading_desk.html`。

数据来源：
- 现金 / 持仓 / 止损止盈：`PORTFOLIO.md`（唯一事实来源）
- 实时价、指数：`data_sources.quote`（腾讯，直连）
- 走势缩略图：`data_sources.kline_qfq`（腾讯前复权日线）

用法：
    .venv/Scripts/python.exe tools/build_trading_desk.py
    .venv/Scripts/python.exe tools/build_trading_desk.py --no-kline   # 不画缩略图，更快
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import data_sources as ds  # noqa: E402

PORTFOLIO = ROOT / "PORTFOLIO.md"
OUT = ROOT / "trading_desk.html"

INDICES = [("000001", "上证指数"), ("399001", "深证成指"), ("399006", "创业板指")]


def _num(text: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(match.group()) if match else None


def _section_table(markdown: str, heading: str) -> list[str]:
    lines = markdown.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(heading))
    except StopIteration:
        return []
    table: list[str] = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if line.lstrip().startswith("|"):
            table.append(line.strip())
    return table


def _rows(table: list[str]) -> list[list[str]]:
    parsed = [[cell.strip() for cell in row.strip("|").split("|")] for row in table]
    parsed = [r for r in parsed if not all(set(c) <= set("-: ") for c in r if c)]
    return parsed[1:] if parsed else []


def load_portfolio() -> dict:
    markdown = PORTFOLIO.read_text(encoding="utf-8")

    cash = None
    for row in _rows(_section_table(markdown, "## 账户")):
        if row and row[0].startswith("现金"):
            cash = _num(row[1])

    holdings = []
    for row in _rows(_section_table(markdown, "## 持仓与止损止盈")):
        if len(row) < 8:
            continue
        name, code, qty, cost, _, stop, reduce_rule, target = row[:8]
        holdings.append({
            "name": name.replace("**", ""),
            "code": code.replace("**", ""),
            "symbol": code.split(".")[0].replace("**", ""),
            "qty": int(_num(qty) or 0),
            "cost": _num(cost),
            "stop": _num(stop),
            "target": _num(target),
            "target_text": target.replace("**", ""),
            "reduce_rule": reduce_rule.replace("**", ""),
        })

    watchlist = []
    for row in _rows(_section_table(markdown, "## 候选池")):
        if len(row) < 7:
            continue
        name, code, band, stop, target, price, status = row[:7]
        watchlist.append({
            "name": name, "code": code, "band": band.replace("**", ""),
            "stop": _num(stop), "target": _num(target), "price": _num(price),
            "status": status.replace("**", ""),
        })

    ratings = []
    for row in _rows(_section_table(markdown, "## 今日分析记录")):
        if len(row) < 4:
            continue
        ratings.append({"name": row[0], "rating": row[1], "target": row[2], "horizon": row[3]})

    return {"cash": cash or 0.0, "holdings": holdings, "watchlist": watchlist, "ratings": ratings}


def sparkline(closes: list[float], width: int = 120, height: int = 32) -> str:
    if len(closes) < 2:
        return ""
    low, high = min(closes), max(closes)
    span = (high - low) or 1
    step = width / (len(closes) - 1)
    points = " ".join(
        f"{i * step:.1f},{height - (c - low) / span * (height - 4) - 2:.1f}"
        for i, c in enumerate(closes)
    )
    color = "#f0453f" if closes[-1] >= closes[0] else "#22a06b"
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
        f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.6"/></svg>'
    )


def fmt(value: float | None, digits: int = 2, suffix: str = "") -> str:
    return "—" if value is None else f"{value:,.{digits}f}{suffix}"


def signed(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    cls = "up" if value > 0 else ("down" if value < 0 else "flat")
    return f'<span class="{cls}">{value:+,.{digits}f}</span>'


def build(args) -> str:
    book = load_portfolio()
    quotes = ds.quote([h["symbol"] for h in book["holdings"]]) if book["holdings"] else {}
    index_quotes = ds.quote([code for code, _ in INDICES], index=True)

    market_value = 0.0
    holdings_html = []
    triggers: list[str] = []

    for item in book["holdings"]:
        q = quotes.get(item["symbol"], {})
        price = q.get("px")
        pct = q.get("pct")
        high, low = q.get("high"), q.get("low")
        value = (price or 0) * item["qty"]
        market_value += value

        pnl = None if (item["cost"] is None or price is None) else (price - item["cost"]) * item["qty"]
        to_stop = None if (item["stop"] is None or price is None) else (price / item["stop"] - 1) * 100
        to_target = None if (item["target"] is None or price is None) else (item["target"] / price - 1) * 100

        if price is not None and item["stop"] is not None and price <= item["stop"]:
            triggers.append(f"{item['name']} 触发 A：现价 {price:.2f} ≤ 止损 {item['stop']:.2f}")
        if price is not None and item["target"] is not None and price >= item["target"]:
            triggers.append(f"{item['name']} 触发 A：现价 {price:.2f} ≥ 目标 {item['target']:.2f}")
        if pct is not None and abs(pct) >= 1:
            triggers.append(f"{item['name']} 触发 B：单日 {pct:+.2f}%")

        progress = 0.0
        if item["stop"] and item["target"] and price and item["target"] > item["stop"]:
            progress = max(0.0, min(1.0, (price - item["stop"]) / (item["target"] - item["stop"])))

        closes: list[float] = []
        if not args.no_kline:
            frame = ds.kline_qfq(item["symbol"], 200)
            if frame is not None and len(frame) >= 10:
                closes = [float(x) for x in frame["close"].tail(40).tolist()]

        holdings_html.append(f"""
        <article class="card holding">
          <header class="holding-head">
            <div>
              <h3>{html.escape(item['name'])} <span class="code">{html.escape(item['code'])}</span></h3>
              <p class="muted">{item['qty']} 股 · 成本 {fmt(item['cost'])}</p>
            </div>
            <div class="price-block {('up' if (pct or 0) > 0 else 'down' if (pct or 0) < 0 else 'flat')}">
              <strong data-quote="{item['symbol']}">{fmt(price)}</strong>
              <span data-pct="{item['symbol']}">{'—' if pct is None else f'{pct:+.2f}%'}</span>
            </div>
          </header>
          {sparkline(closes) if closes else ''}
          <dl class="metrics">
            <div><dt>市值</dt><dd>{fmt(value)}</dd></div>
            <div><dt>浮动盈亏</dt><dd>{('—' if pnl is None else signed(pnl))}</dd></div>
            <div><dt>日内</dt><dd data-range="{item['symbol']}">{fmt(low)} – {fmt(high)}</dd></div>
            <div><dt>止损</dt><dd class="down">{fmt(item['stop'])} <small>{'' if to_stop is None else f'{to_stop:+.2f}%'}</small></dd></div>
            <div><dt>目标</dt><dd class="up">{html.escape(item['target_text'])} <small>{'' if to_target is None else f'{to_target:+.2f}%'}</small></dd></div>
            <div><dt>距止损</dt><dd>{'' if to_stop is None else f'{to_stop:+.2f}%'}</dd></div>
          </dl>
          <div class="track" title="止损 → 现价 → 目标"><i style="width:{progress * 100:.1f}%"></i></div>
          <p class="rule">{html.escape(item['reduce_rule'])}</p>
        </article>""")

    equity = (book["cash"] or 0) + market_value
    exposure = (market_value / equity * 100) if equity else 0

    index_html = []
    for code, label in INDICES:
        q = index_quotes.get(code, {})
        pct = q.get("pct") or 0
        if pct <= -2:
            triggers.append(f"{label} 触发 C：单日 {pct:.2f}%")
        index_html.append(f"""
        <div class="index">
          <span class="muted">{label}</span>
          <strong data-quote="{code}">{fmt(q.get('px'))}</strong>
          <span class="{'up' if pct > 0 else 'down' if pct < 0 else 'flat'}" data-pct="{code}">{pct:+.2f}%</span>
          <small class="muted" data-range="{code}">{fmt(q.get('low'))} – {fmt(q.get('high'))}</small>
        </div>""")

    watch_html = "".join(f"""
      <tr>
        <td>{html.escape(w['name'])}<span class="code">{html.escape(w['code'])}</span></td>
        <td>{html.escape(w['band'])}</td>
        <td>{fmt(w['price'])}</td>
        <td class="down">{fmt(w['stop'])}</td>
        <td class="up">{fmt(w['target'])}</td>
        <td>{html.escape(w['status'])}</td>
      </tr>""" for w in book["watchlist"])

    rating_html = "".join(f"""
      <tr><td>{html.escape(r['name'])}</td><td><span class="badge">{html.escape(r['rating'])}</span></td>
      <td>{html.escape(r['target'])}</td><td class="muted">{html.escape(r['horizon'])}</td></tr>"""
                          for r in book["ratings"])

    trigger_text = "无触发" if not triggers else "；".join(triggers)
    trigger_class = "ok" if not triggers else "alert"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    template = (ROOT / "tools" / "trading_desk_template.html").read_text(encoding="utf-8")
    return (template
            .replace("{{STAMP}}", stamp)
            .replace("{{CASH}}", fmt(book["cash"]))
            .replace("{{MARKET_VALUE}}", fmt(market_value))
            .replace("{{EQUITY}}", fmt(equity))
            .replace("{{EXPOSURE}}", f"{exposure:.1f}")
            .replace("{{INDEX_CARDS}}", "".join(index_html))
            .replace("{{HOLDINGS}}", "".join(holdings_html) or '<p class="muted">无持仓</p>')
            .replace("{{WATCHLIST}}", watch_html or '<tr><td colspan="6" class="muted">候选池为空</td></tr>')
            .replace("{{RATINGS}}", rating_html or '<tr><td colspan="4" class="muted">今日无分析记录</td></tr>')
            .replace("{{TRIGGER_TEXT}}", html.escape(trigger_text))
            .replace("{{TRIGGER_CLASS}}", trigger_class))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-kline", action="store_true", help="跳过缩略图，少请求几次行情")
    args = parser.parse_args()
    OUT.write_text(build(args), encoding="utf-8")
    print(f"写入 {OUT}（{OUT.stat().st_size / 1024:.1f} KB）")


if __name__ == "__main__":
    main()
