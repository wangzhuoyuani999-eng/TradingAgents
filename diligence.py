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
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "data" / "logs" / "reports"
LOGS = ROOT / "data" / "logs"

# CLI 默认把报告写到 ~/.tradingagents/logs；统一改成仓库内，父进程和子进程都要看到同一个值
# （否则 _newest_report 在父进程里找不到刚跑出来的新目录，会退回旧报告 —— 2026-11-25 踩过）。
os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR", str(REPORTS))

RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")

# Magpie 网关里的模型路由。opendesign/* 要绕到 Open Design 云端，
# 网络不通时会直接超时；auto/deepseek-* 由网关就近路由，通常更稳。
# 老的 deepseek/deepseek-flash、deepseek/deepseek-v4-pro 在当前网关已 404。
DEFAULT_FALLBACKS = ("auto/deepseek-v4.1-flash", "auto/deepseek-v4.1-flash-eco")


def _probe_model(model: str, timeout: int = 20) -> tuple[bool, str]:
    """用一次 8 token 的调用探活，返回 (可用, 说明)。

    20 秒内没回到就当作不可用——真跑一次分析要 7-8 分钟，
    在这种网络下换模型比等它超时划算得多。
    """
    import json
    import urllib.error
    import urllib.request

    base = os.environ.get("TRADINGAGENTS_LLM_BACKEND_URL", "http://127.0.0.1:3425/v1").rstrip("/")
    key = os.environ.get("OPENAI_API_KEY", "magpie")
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
        "stream": False,
    }
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            json.loads(r.read())
        return True, f"{time.time() - started:.1f}s"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} ({time.time() - started:.1f}s)"
    except Exception as e:  # noqa: BLE001 — 任何异常都算探活失败
        return False, f"{type(e).__name__} ({time.time() - started:.1f}s)"


def _pick_model(preferred: str | None, fallbacks: tuple[str, ...]) -> tuple[str, list[str]]:
    """先探首选模型，不通就按顺序找可用的备选。返回 (要用的模型, 探活日志)。"""
    log: list[str] = []
    primary = preferred or os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM", "")
    candidates = [primary, *fallbacks] if primary else list(fallbacks)
    seen = set()
    for model in candidates:
        if not model or model in seen:
            continue
        seen.add(model)
        ok, detail = _probe_model(model)
        log.append(f"{model}: {'可用' if ok else '不可用'} {detail}")
        if ok:
            return model, log
    return "", log


def _run_one(ticker: str, date: str, analysts: str, timeout: int, model: str = "") -> dict:
    """跑一次 TradingAgents，返回 {ticker, ok, rating, summary, report_dir, error}。"""
    started = datetime.now()
    cmd = [
        str(ROOT / "run.cmd"),
        "--ticker", ticker,
        "--date", date,
        "--analysts", analysts,
        "--save", "--no-show", "--no-html", "--no-checkpoint",
    ]
    env = dict(os.environ)
    # CLI 默认写 ~/.tradingagents/logs；统一落到仓库 data/logs/reports，
    # 免得报告散在用户目录、且 relative_to(ROOT) 直接崩（2026-11-25 踩过）。
    env.setdefault("TRADINGAGENTS_RESULTS_DIR", str(ROOT / "data" / "logs" / "reports"))
    if model:
        # 探活选中的模型优先于 .env 里的配置
        env["TRADINGAGENTS_QUICK_THINK_LLM"] = model
        env["TRADINGAGENTS_DEEP_THINK_LLM"] = model
    err = ""
    timed_out = False
    if os.name == "nt":
        # run.cmd 会再派生一个 python；只用 subprocess.run 的 timeout 只杀直接子进程，
        # 孙进程会继续占着 stdout 管道把父进程卡死（实测过）。所以自己管进程树。
        proc = subprocess.Popen(
            cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        try:
            _, err_out = proc.communicate(timeout=timeout)
            err = (err_out or "")[-400:]
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, check=False,
            )
            try:
                proc.communicate(timeout=30)
            except Exception:  # noqa: BLE001 — 已尽力清理
                pass
    else:
        try:
            p = subprocess.run(
                cmd, cwd=str(ROOT), capture_output=True, text=True,
                timeout=timeout, encoding="utf-8", errors="replace", env=env,
            )
            err = (p.stderr or "")[-400:]
        except subprocess.TimeoutExpired:
            timed_out = True

    if timed_out:
        # 报告可能在进程卡住之前就写完了（2026-11-19 的 603118 就是这样：
        # decision.md 已经落盘，但进程在收尾阶段超过 900s）。先看产物再判失败。
        late = _newest_report(ticker, date)
        rating, summary = _parse_decision(late) if late else (None, None)
        if rating:
            return {"ticker": ticker, "ok": True, "rating": rating, "summary": summary,
                    "report_dir": _rel(late),
                    "error": f"进程超时 >{timeout}s，但报告已生成，按已生成结果采用",
                    "model": model,
                    "elapsed_s": round((datetime.now() - started).total_seconds(), 1)}
        return {"ticker": ticker, "ok": False, "rating": None, "summary": None,
                "report_dir": None, "error": f"超时 >{timeout}s，且未产出 decision.md",
                "model": model,
                "elapsed_s": round((datetime.now() - started).total_seconds(), 1)}

    report = _newest_report(ticker, date)
    if report is None:
        return {"ticker": ticker, "ok": False, "rating": None, "summary": None,
                "report_dir": None, "error": f"未生成报告目录。stderr: {err}".strip(),
                "model": model,
                "elapsed_s": round((datetime.now() - started).total_seconds(), 1)}

    rating, summary = _parse_decision(report)
    return {
        "ticker": ticker,
        "ok": rating is not None,
        "rating": rating,
        "summary": summary,
        "report_dir": _rel(report),
        "error": None if rating else "decision.md 里没解析出 Rating",
        "elapsed_s": round((datetime.now() - started).total_seconds(), 1),
    }


def _rel(path: Path) -> str:
    """报告目录可能落在仓库外（CLI 默认 ~/.tradingagents/logs），取不到相对路径就返回绝对路径。"""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _results_root() -> Path:
    """CLI 实际写报告的位置。

    `default_config` 的 results_dir = TRADINGAGENTS_RESULTS_DIR 或
    ~/.tradingagents/logs，再拼 `<ticker>/<YYYY-MM-DD>`；旧版本曾用
    `data/logs/reports/<ticker>_<date>_<time>`，两条路径都要认。
    """
    env = os.environ.get("TRADINGAGENTS_RESULTS_DIR")
    if env:
        return Path(env)
    return Path.home() / ".tradingagents" / "logs"


def _newest_report(ticker: str, date: str) -> Path | None:
    """本次运行产生的报告目录：新布局 `<root>/<ticker>/<date>` 优先，其次旧的扁平目录。"""
    cands: list[Path] = []
    new_layout = _results_root() / ticker / date
    if new_layout.is_dir():
        cands.append(new_layout)
    stem = f"{ticker}_{date.replace('-', '')}_"
    if REPORTS.exists():
        cands.extend(d for d in REPORTS.glob(stem + "*") if d.is_dir())
    return max(cands, key=lambda d: d.stat().st_mtime) if cands else None


def _parse_decision(report_dir: Path) -> tuple[str | None, str | None]:
    """提取 Rating 与 Executive Summary：新布局 reports/final_trade_decision.md，
    旧布局 5_portfolio/decision.md（两者其一有 Rating 就算成功）。"""
    for p in (report_dir / "reports" / "final_trade_decision.md",
              report_dir / "5_portfolio" / "decision.md"):
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")

        m = re.search(r"\*\*Rating\*\*\s*[:：]\s*([A-Za-z]+)", text)
        rating = m.group(1).capitalize() if m else None
        if rating and rating not in RATINGS:
            rating = None

        s = re.search(r"\*\*Executive Summary\*\*\s*[:：]\s*(.+?)(?:\n\s*\n|\Z)", text, re.S)
        summary = re.sub(r"\s+", " ", s.group(1)).strip() if s else None
        if summary and len(summary) > 400:
            summary = summary[:400] + "…"
        if rating:
            return rating, summary
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser(description="候选标的深度尽调")
    ap.add_argument("--tickers", required=True, help="逗号分隔，如 600885.SS,002415.SZ")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--analysts", default="market,news,fundamentals")
    ap.add_argument("--timeout", type=int, default=900, help="单只超时秒数")
    ap.add_argument("--model", default="", help="指定模型，留空则用 .env 的配置并自动探活")
    ap.add_argument(
        "--fallbacks", default=",".join(DEFAULT_FALLBACKS),
        help="首选不可用时的备选模型，逗号分隔",
    )
    ap.add_argument("--no-probe", action="store_true", help="跳过探活，直接用 .env 配置")
    args = ap.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    model = args.model
    probe_log: list[str] = []
    if not args.no_probe:
        fallbacks = tuple(m.strip() for m in args.fallbacks.split(",") if m.strip())
        model, probe_log = _pick_model(args.model or None, fallbacks)
        print("模型探活：", flush=True)
        for line in probe_log:
            print(f"  {line}", flush=True)
        if not model:
            print("\n没有可用模型，放弃本次尽调（不阻塞当日决策）。", flush=True)
            LOGS.mkdir(parents=True, exist_ok=True)
            (LOGS / f"diligence_{args.date.replace('-', '')}.json").write_text(
                json.dumps({
                    "date": args.date,
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "analysts": args.analysts,
                    "probe": probe_log,
                    "results": [],
                    "error": "没有可用模型",
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return 2
        print(f"使用模型：{model}\n", flush=True)

    results: list[dict] = []

    for i, tk in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] 尽调 {tk} …（预计 7-8 分钟）", flush=True)
        r = _run_one(tk, args.date, args.analysts, args.timeout, model)
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
        "model": model,
        "probe": probe_log,
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
