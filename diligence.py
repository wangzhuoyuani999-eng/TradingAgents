"""对候选标的跑 TradingAgents 深度尽调，提取评级并汇总。

设计原则：
- 规则负责"能不能买"，LLM 负责"该不该买"。这里只做尽调，不改买点。
- 失败不阻塞：单个标的超时/报错就记下来，继续跑下一个，绝不阻塞当日决策。
- 绝不复用旧报告顶替（数据过期比没有更危险）。

用法：
    python diligence.py --tickers 600885.SS,002415.SZ
    python diligence.py --tickers 600885.SS --date 2026-11-18 --analysts market,news,fundamentals
    python diligence.py --tickers 600885.SS --timeout 720

输出：
    data/logs/diligence_<YYYYMMDD>.json   （结构化结果）
    标准输出                              （人读摘要）
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "data" / "logs" / "reports"
LOGS = ROOT / "data" / "logs"

RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")


def _run_one(ticker: str, date: str, analysts: str, timeout: int) -> dict:
    """跑一次 TradingAgents，返回 {ticker, ok, rating, summary, report_dir, error}。"""
    started = datetime.now()
    cmd = [
        str(ROOT / "run.cmd"),
        "--ticker", ticker,
        "--date", date,
        "--analysts", analysts,
        "--save", "--no-show", "--no-html", "--no-checkpoint",
    ]
    err = ""
    try:
        p = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        # run.cmd 正常结束时也可能返回 1（cli_prefs 权限问题），所以不看返回码，看产物
        err = (p.stderr or "")[-400:]
    except subprocess.TimeoutExpired:
        return {"ticker": ticker, "ok": False, "rating": None, "summary": None,
                "report_dir": None, "error": f"超时 >{timeout}s",
                "elapsed_s": round((datetime.now() - started).total_seconds(), 1)}

    report = _newest_report(ticker, date)
    if report is None:
        return {"ticker": ticker, "ok": False, "rating": None, "summary": None,
                "report_dir": None, "error": f"未生成报告目录。stderr: {err}".strip(),
                "elapsed_s": round((datetime.now() - started).total_seconds(), 1)}

    rating, summary = _parse_decision(report)
    return {
        "ticker": ticker,
        "ok": rating is not None,
        "rating": rating,
        "summary": summary,
        "report_dir": str(report.relative_to(ROOT)),
        "error": None if rating else "decision.md 里没解析出 Rating",
        "elapsed_s": round((datetime.now() - started).total_seconds(), 1),
    }


def _newest_report(ticker: str, date: str) -> Path | None:
    """本次运行产生的报告目录：<ticker>_<dateYYYYMMDD>_<HHMMSS>，取最新的一个。"""
    stem = f"{ticker}_{date.replace('-', '')}_"
    cands = [d for d in REPORTS.glob(stem + "*") if d.is_dir()] if REPORTS.exists() else []
    return max(cands, key=lambda d: d.stat().st_mtime) if cands else None


def _parse_decision(report_dir: Path) -> tuple[str | None, str | None]:
    """从 5_portfolio/decision.md 提取 Rating 与 Executive Summary。"""
    p = report_dir / "5_portfolio" / "decision.md"
    if not p.exists():
        return None, None
    text = p.read_text(encoding="utf-8", errors="replace")

    m = re.search(r"\*\*Rating\*\*\s*[:：]\s*([A-Za-z]+)", text)
    rating = m.group(1).capitalize() if m else None
    if rating and rating not in RATINGS:
        rating = None

    s = re.search(r"\*\*Executive Summary\*\*\s*[:：]\s*(.+?)(?:\n\s*\n|\Z)", text, re.S)
    summary = re.sub(r"\s+", " ", s.group(1)).strip() if s else None
    if summary and len(summary) > 400:
        summary = summary[:400] + "…"
    return rating, summary


def main() -> int:
    ap = argparse.ArgumentParser(description="候选标的深度尽调")
    ap.add_argument("--tickers", required=True, help="逗号分隔，如 600885.SS,002415.SZ")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--analysts", default="market,news,fundamentals")
    ap.add_argument("--timeout", type=int, default=900, help="单只超时秒数")
    args = ap.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    results: list[dict] = []

    for i, tk in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] 尽调 {tk} …（预计 7-8 分钟）", flush=True)
        r = _run_one(tk, args.date, args.analysts, args.timeout)
        results.append(r)
        if r["ok"]:
            print(f"  → 评级 {r['rating']}｜{r['elapsed_s']}s｜{r['report_dir']}")
        else:
            print(f"  → 失败：{r['error']}")

    LOGS.mkdir(parents=True, exist_ok=True)
    out = LOGS / f"diligence_{args.date.replace('-', '')}.json"
    payload = {
        "date": args.date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "analysts": args.analysts,
        "results": results,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = [r for r in results if r["ok"]]
    print(f"\n完成 {len(ok)}/{len(results)}｜结果写入 {out.relative_to(ROOT)}")
    for r in results:
        if r["ok"]:
            print(f"  {r['ticker']:12} {r['rating']:12} {r['summary'][:90] if r['summary'] else ''}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
