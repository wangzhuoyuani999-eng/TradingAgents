"""实盘成交台账（strategy_trades.jsonl）——迭代纪律的计数器。

为什么需要它：`research/策略迭代日志.md` 规定「实盘累计 20 笔」才触发策略复盘，
但 2026-11-27 之前的 4 笔实盘交易**一笔都没记录**，等于计数器从没启动。

字段（与迭代日志一致）：
    ticker / name / entry_date / entry / stop / shares / score /
    exit_date / exit / ret / reason / system

用法：
    # 记一笔已了结交易
    .venv/Scripts/python.exe tools/trade_log.py add --ticker 600428.SS --name 中远海特 \
        --entry-date 2026-11-24 --entry 10.99 --stop 10.45 --shares 100 \
        --exit-date 2026-11-26 --exit 10.82 --reason "减仓线破位" --system 0

    # 看统计（胜率/PF/距离 20 笔还差多少）
    .venv/Scripts/python.exe tools/trade_log.py stats

    # 原始记录
    .venv/Scripts/python.exe tools/trade_log.py show

口径：ret = exit/entry - 1（未扣费用）；`system=1` 表示策略信号产生，`0` 表示人工/建账带入。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "logs" / "strategy_trades.jsonl"
THRESHOLD = 20  # 迭代日志：累计 20 笔实盘触发复盘


def load() -> list[dict]:
    if not LOG.exists():
        return []
    rows = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def append(row: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def cmd_add(args) -> int:
    if not args.entry or not args.exit:
        print("[x] entry/exit 必填", file=sys.stderr)
        return 2
    row = {
        "ticker": args.ticker,
        "name": args.name,
        "entry_date": args.entry_date,
        "entry": round(float(args.entry), 3),
        "stop": round(float(args.stop), 3) if args.stop else None,
        "shares": int(args.shares),
        "score": args.score,
        "exit_date": args.exit_date,
        "exit": round(float(args.exit), 3),
        "ret": round(float(args.exit) / float(args.entry) - 1, 5),
        "reason": args.reason,
        "system": int(args.system),
    }
    append(row)
    rows = load()
    print(f"已记录：{row['ticker']} {row['name']} {row['entry_date']}→{row['exit_date']} "
          f"ret {row['ret']*100:+.2f}%  累计 {len(rows)} 笔")
    return 0


def cmd_stats(_args) -> int:
    rows = load()
    if not rows:
        print("台账为空。用 `add` 补录。")
        return 0
    closed = [r for r in rows if r.get("exit") is not None]
    wins = [r for r in closed if r["ret"] > 0]
    losses = [r for r in closed if r["ret"] <= 0]
    gross_win = sum(r["ret"] for r in wins)
    gross_loss = abs(sum(r["ret"] for r in losses))
    pf = (gross_win / gross_loss) if gross_loss else float("inf")
    print(f"已了结交易      {len(closed)} 笔（另有未了结 {len(rows) - len(closed)} 笔）")
    print(f"胜率            {len(wins)/len(closed)*100:.1f}%")
    print(f"平均每笔        {(sum(r['ret'] for r in closed)/len(closed))*100:+.2f}%")
    print(f"盈亏比 PF       {pf:.2f}")
    print(f"策略信号笔数    {sum(1 for r in rows if r.get('system') == 1)} 笔")
    print(f"迭代门槛        {len(closed)}/{THRESHOLD} 笔 → 还差 {max(0, THRESHOLD - len(closed))} 笔")
    print(f"偏离告警线      {'已触发复盘条件' if len(closed) >= THRESHOLD and (len(wins)/len(closed) < 0.25 or pf < 1.1) else '未触发'}")
    for r in closed:
        print(f"  {r['ticker']:10s} {r['name']:6s} {r['entry_date']}→{r['exit_date']} "
              f"{r['entry']}→{r['exit']} ret {r['ret']*100:+.2f}%  {r.get('reason') or ''}")
    return 0


def cmd_show(_args) -> int:
    rows = load()
    print(f"{len(rows)} 条记录（{LOG.relative_to(ROOT)}）")
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="实盘成交台账")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="追加一笔已了结交易")
    a.add_argument("--ticker", required=True)
    a.add_argument("--name", required=True)
    a.add_argument("--entry-date", required=True)
    a.add_argument("--entry", required=True, type=float)
    a.add_argument("--stop", type=float, default=None)
    a.add_argument("--shares", required=True, type=int)
    a.add_argument("--score", type=float, default=None)
    a.add_argument("--exit-date", required=True)
    a.add_argument("--exit", required=True, type=float)
    a.add_argument("--reason", default="")
    a.add_argument("--system", type=int, default=0, choices=(0, 1))
    a.set_defaults(func=cmd_add)

    s = sub.add_parser("stats", help="统计胜率/PF/迭代进度")
    s.set_defaults(func=cmd_stats)

    h = sub.add_parser("show", help="打印全部记录")
    h.set_defaults(func=cmd_show)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
