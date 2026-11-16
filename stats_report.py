"""汇总 data/logs/run_stats.jsonl 里每次运行的开销。

用法：
    python stats_report.py            # 每次一行 + 合计
    python stats_report.py --json     # 原始 JSON 行

每次 `tradingagents` 跑完都会往这个文件追加一行（tokens、调用次数、耗时、
评级）。批量跑完十只以后，一条命令就能看到这一轮总共花了多少 token。
"""

import argparse
import json
import sys
from pathlib import Path

LOG = Path("data/logs/run_stats.jsonl")


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a half-written line from a killed run
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize TradingAgents token usage")
    parser.add_argument("--json", action="store_true", help="print the raw records")
    parser.add_argument("--log", default=str(LOG), help="path to run_stats.jsonl")
    args = parser.parse_args()

    rows = load(Path(args.log))
    if not rows:
        print(f"没有找到记录：{args.log}")
        return 1

    if args.json:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))
        return 0

    header = f"{'时间':<17}{'标的':<12}{'分析师':<10}{'评级':<12}{'调用':>5}{'输入':>10}{'输出':>9}{'合计':>10}{'秒':>6}"
    print(header)
    print("-" * len(header))
    for r in rows:
        analysts = ",".join(r.get("analysts") or [])[:9]
        print(
            f"{r.get('generated_at', '')[:16]:<17}"
            f"{r.get('ticker', ''):<12}{analysts:<10}{r.get('rating', ''):<12}"
            f"{r.get('llm_calls', 0):>5}{r.get('tokens_in', 0):>10,}"
            f"{r.get('tokens_out', 0):>9,}{r.get('total_tokens', 0):>10,}"
            f"{r.get('elapsed_seconds', 0):>6.0f}"
        )

    total = sum(r.get("total_tokens", 0) for r in rows)
    tin = sum(r.get("tokens_in", 0) for r in rows)
    tout = sum(r.get("tokens_out", 0) for r in rows)
    calls = sum(r.get("llm_calls", 0) for r in rows)
    secs = sum(r.get("elapsed_seconds", 0) for r in rows)
    print("-" * len(header))
    print(
        f"{'合计 ' + str(len(rows)) + ' 次':<17}{'':<12}{'':<10}{'':<12}"
        f"{calls:>5}{tin:>10,}{tout:>9,}{total:>10,}{secs:>6.0f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
