---
name: a-share-trading-desk
description: A 股实盘交易台的日常操作流程——盘前分析、开盘执行、盘中巡检、收盘总结、收盘选股，以及成交后的记账。当用户要盯盘、要下单指令、要止损/止盈判断、要收盘复盘或要更新候选池时使用。
whenToUse: 交易日需要盘前计划、盘中巡检、下单决策、收盘总结或选股复盘；或需要核对持仓、候选池与风控额度。
---

# A 股交易台操作流程

本工作区是 **A 股实盘跟踪 + TradingAgents 分析**环境。
`AGENTS.md` 已自动加载，规定了输出格式与风控硬约束；本 skill 只补它没写的**工作流**。
两者冲突时，以 `AGENTS.md` 为准。

## 0. 铁律（每次动手前先过一遍）

- **只做沪深主板**：000/001/002/003/600/601/603/605。
  **创业板 300/301、科创板 688/689 买不了（无权限）**；北交所 4/8、B 股 9 开头不做。
  输出里一旦出现 300/301/688/689，说明过滤失效 → **报警，且不要写入候选池**。
- **一天最多买一只。**
- **止损用收盘确认制**：盘中破位不砍，收盘确认后**下一个交易日**执行；跳空跌破则开盘执行。
- **单笔风险 ≤ 总权益 1%**（按止损距离算）；单只 ≤65%；总仓 ≤85%。
- **需要下单时**必须用 `## ⚠️ 需要你下单` + 表格（标的/方向/价格/数量/止损/有效期）；
  不需要就明确写「**今天不需要下单**」。
- 持仓、现金、候选池**以 `data/trading_desk/*.json` 为准**，不要用对话里记的旧数字。

## 1. 每日节奏

| 时间 | 动作 | 产出 |
|---|---|---|
| 08:30 | **盘前分析**：隔夜外盘 + 周末/隔夜消息 + 持仓位置 | 动作结论（清/留/加）+ 下单表 |
| 09:25 | **开盘指令**：读集合竞价价，按开盘位置分档给指令 | 具体成交价区间 |
| 09:35 起每 10 分钟 | **盘中巡检**：只在触发条件时推飞书 | 见 `references/triggers.md` |
| 11:25 | 上午总结（固定推） | 半日盈亏 + 关键位 |
| 14:55 | 收盘总结（固定推） | 全天结果 + 明日计划 |
| 15:10 | **收盘选股**：跑 `screen_v3.py`，刷新候选池 | 候选表 + 明日买区 |

**非交易时段**（含午休）巡检只回一句「非交易时段，跳过」，**不推飞书**。

## 2. 脚本速查

全部用 `./.venv/Scripts/python.exe` 跑，工作目录为仓库根。

| 脚本 | 用途 | 典型调用 |
|---|---|---|
| `data_sources.py` | 数据层（不直接跑，被其它脚本 import） | `ds.quote(["600111"])` / `ds.quote(["000001"], index=True)` |
| `watch_quotes.py` | 批量看持仓报价 | `python watch_quotes.py` |
| `screen_v3.py` | **4 层选股漏斗**（主力选股器） | `python screen_v3.py --limit 400 --top 10` |
| `backtest_v3.py` | 组合回测 + 指数择时 | `python backtest_v3.py` |
| `backtest_strata.py` | 按基本面分层的回测 | `python backtest_strata.py` |
| `strategy_stats.py` | 实盘成交统计 vs 回测基线 | `python strategy_stats.py` |
| `cost_ledger.py` | 分析成本台账 | `python cost_ledger.py` |

选股结果写入 `data/logs/screen_v3_<YYYYMMDD>.json`。

## 3. 交易台读写

用 `trading_desk_read` / `trading_desk_write` 工具，**不要直接改 JSON**。

- `view=overview|positions|watchlist|records|journal|strategies|decision`
- `action=upsert_position|remove_position|set_cash|add_note|save_plan|save_watchlist|delete_journal`

**成交后的固定顺序**（顺序不能乱）：

1. 买入成交 → `upsert_position`（ticker/name/quantity/averagePrice/stopLoss/targetPrice）
2. 卖出成交 → `remove_position`（清仓）或 `upsert_position`（减仓，quantity 改小、averagePrice 不变）
3. 现金变化 → `set_cash`
4. 当日复盘 → `add_note`（date=成交日）
5. 次日计划 → `save_plan`（date=下一交易日）
6. 候选池 → `save_watchlist`

## 4. 详细流程（按需读取）

| 需要做什么 | 读哪个文件 |
|---|---|
| 定巡检触发条件、按价位分档做清/留决策 | `references/triggers.md` |
| 盘前 / 开盘 / 收盘 / 选股的完整步骤与模板 | `references/workflows.md` |
| 数据源细节、踩过的坑、排错顺序 | `references/pitfalls.md` |

## 5. 判断口径（别每次都重新发明）

- **趋势优先于便宜**：跌破 MA20 的票不接，MA20 在下移的票不接。
- **买点位置比分数重要**：同分两只票，回踩企稳的 vs 跌破均线继续杀的，只买前者。
- **止损收到保本**是减仓后的默认动作，不是可选项。
- **一天只买一只**是纪律，不是建议——它是多次避免踩雷的主因。
- 候选池长期只有 0–3 只合格标的属于正常，**不要为了出手而降低门槛**。
