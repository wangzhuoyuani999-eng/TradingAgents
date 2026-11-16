"""实盘 vs 回测对比：读 data/logs/strategy_trades.jsonl，算胜率/盈亏比/期望。

用法：
    python strategy_stats.py            # 汇总
    python strategy_stats.py --add ...  # 不提供，用 JSONL 直接追加即可

每行一个 JSON：
{"ticker":"600111.SS","name":"北方稀土","entry_date":"2026-11-09","entry":36.40,
 "stop":35.80,"shares":200,"score":4,"exit_date":null,"exit":null,"ret":null,
 "reason":"","system":0}
"""

from __future__ import annotations

import json
import os
import sys

PATH = "data/logs/strategy_trades.jsonl"

# v1.0 回测基线
BASELINE = {"win_rate": 0.367, "avg_ret": 0.0103, "pf": 1.52, "mdd": -0.174}


def load() -> list[dict]:
    if not os.path.exists(PATH):
        return []
    rows = []
    with open(PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    rows = load()
    closed = [r for r in rows if isinstance(r.get("ret"), (int, float))]
    opened = [r for r in rows if not isinstance(r.get("ret"), (int, float))]

    print(f"记录 {len(rows)} 笔：持仓中 {len(opened)}，已平仓 {len(closed)}")

    if opened:
        print("\n持仓中：")
        for r in opened:
            tag = "系统内" if r.get("system") else "系统外"
            print(f"  {r['ticker']} {r.get('name','')} {r.get('shares')}股 @{r.get('entry')} "
                  f"止损 {r.get('stop')} · 评分 {r.get('score')} · {tag}")

    if not closed:
        print("\n还没有已平仓交易，无法与回测对比。")
        return

    wins = [r["ret"] for r in closed if r["ret"] > 0]
    losses = [r["ret"] for r in closed if r["ret"] <= 0]
    wr = len(wins) / len(closed)
    avg = sum(r["ret"] for r in closed) / len(closed)
    pf = (sum(wins) / abs(sum(losses))) if losses else float("inf")

    print("\n已平仓统计：")
    print(f"  胜率        {wr * 100:.1f}%   （回测 {BASELINE['win_rate'] * 100:.1f}%）")
    print(f"  平均每笔    {avg * 100:+.2f}%  （回测 {BASELINE['avg_ret'] * 100:+.2f}%）")
    print(f"  盈亏比 PF   {pf:.2f}       （回测 {BASELINE['pf']:.2f}）")

    flags = []
    if len(closed) >= 20 and wr < 0.25:
        flags.append("胜率显著低于回测（<25%），需要复盘选股或市场状态")
    if len(closed) >= 20 and pf < 1.1:
        flags.append("盈亏比低于 1.1，赔率优势消失")
    if len(closed) >= 5 and all(r["ret"] <= 0 for r in closed[-5:]):
        flags.append("连续 5 笔亏损，触发迭代评估")

    print("\n" + ("⚠️ " + "；".join(flags) if flags else "✅ 无告警"))
    if len(closed) < 20:
        print(f"（样本 {len(closed)}/20，暂不触发阈值判断）")


if __name__ == "__main__":
    sys.exit(main())
