"""基本面门槛到底有没有用？——把回测交易按「当前净利同比」分层对比。

⚠️ 重要局限：这里用**当前**财务数据去给 2024-2026 的历史交易分类，存在前视偏差
（今天高增长的公司，当年可能并不高增长）。所以结论只能看「方向」，不能看精确数值。
真正无偏的做法要按公告日对齐，当前数据源（新浪/腾讯）拿不到历史财报，只能先这样。

用法： python backtest_strata.py
"""

from __future__ import annotations

import sys

import pandas as pd

import backtest_v3 as bt
import screen_v3 as sv


def main() -> None:
    uni = bt.fetch_universe(150)
    print(f"股票池 {len(uni)} 只")

    trades: list[dict] = []
    for i, row in enumerate(uni.itertuples(), 1):
        k = bt.kline(row.code)
        if k is None:
            continue
        trades.extend(bt.run_stock(row.code, row.name, k))
        if i % 50 == 0:
            print(f"  …{i}/{len(uni)} 交易 {len(trades)}")

    t = pd.DataFrame(trades)
    print(f"\n总交易 {len(t)} 笔")

    growth = {}
    for code in t["code"].unique():
        g = sv.f10_growth(code)
        growth[code] = g.get("yoy_net")
    t["yoy_net"] = t["code"].map(growth)
    known = t["yoy_net"].notna()
    print(f"拿到财务数据 {known.sum()}/{len(t)} 笔（{known.mean() * 100:.0f}%）")

    def stat(df: pd.DataFrame, label: str) -> None:
        if len(df) == 0:
            print(f"{label:<22} 无样本")
            return
        wins = df[df["ret"] > 0]
        losses = df[df["ret"] <= 0]
        pf = wins["ret"].sum() / abs(losses["ret"].sum()) if len(losses) else float("inf")
        print(f"{label:<22} {len(df):>4} 笔  胜率 {len(wins) / len(df) * 100:>5.1f}%  "
              f"平均 {df['ret'].mean() * 100:>+6.2f}%  PF {pf:>5.2f}")

    print("\n=== 按当前净利同比分层 ===")
    stat(t, "全部")
    stat(t[t["yoy_net"] >= 20], "净利同比 ≥ +20%")
    stat(t[(t["yoy_net"] >= 0) & (t["yoy_net"] < 20)], "0% ~ +20%")
    stat(t[t["yoy_net"] < 0], "净利同比 < 0")
    stat(t[t["yoy_net"].isna()], "无数据")


if __name__ == "__main__":
    sys.exit(main())
