# 交易台 · Trading Desk

DSH 插件：把 TradingAgents 工作区里的持仓、盈亏、每日分析记录和每日策略放进 Harness 主面板，并让 Agent 通过工具读写同一份数据。

## 它读什么

只读取，不改动 TradingAgents 自己的产物：

| 来源 | 用途 |
| --- | --- |
| `data/cache/<TICKER>-YFin-data.csv` | 收盘价序列 → 现价、今日涨跌、走势迷你图 |
| `data/logs/reports/<TICKER>_<日期>_<时间>/5_portfolio/decision.md` | 最终评级、目标价、时间框架、执行摘要 |
| `data/logs/reports/.../3_trading/trader.md` | 交易动作、入场价、止损、仓位建议 |
| `data/logs/run_stats.jsonl` | token 用量、耗时、分析师组合（按标的与日期就近匹配） |
| `data/memory/trading_memory.md` | 框架自己的决策记忆（pending / resolved） |

## 它写什么

`data/trading_desk/`，全部是可读的 JSON，可用编辑器直接改：

- `positions.json` — 持仓账本（数量、成本价、止损、目标价、备注、现金、币种）
- `journal.json` — 交易日志与每日计划
- `watchlist.json` — 当日候选池：每只标的的买价区间、触发条件、止损、目标、仓位、理由与状态
- `portfolio_ta.json` — 由账本自动生成的 TradingAgents 组合文件

`portfolio_ta.json` 就是 `tradingagents.portfolio.load_portfolio` 需要的形状，因此下一轮分析可以直接对着你的真实仓位定仓：

```powershell
tradingagents --portfolio data/trading_desk/portfolio_ta.json --ticker 600036.SS
```

**没有行情源的标的**（场外基金、理财、LOF）在持仓里填「手动价格」即可：面板用它算市值与盈亏，并在现价旁标注「手动」，同时记下报价日期；留空则退回按成本价估值。手动价不会自动更新，需要你在面板或通过 `trading_desk_write` 的 `manualPrice` 重新给。

## 面板

左侧栏「交易台」图标 → 主面板四个页签：

- **总览** — 总市值、浮动盈亏、今日盈亏、现金、总权益、仓位；持仓权重条与走势；今日策略。
- **持仓** — 完整表格（成本、现价、市值、盈亏、盈亏比、止损、占比），可增删改；从分析过的标的快速添加；现金与币种。
- **策略** — 按分析日聚合每日策略（评级 / 动作 / 入场 / 止损 / 目标），并为每天写自己的执行计划。
- **候选** — 当日候选池：按优先级列出每只标的的买价区间、触发条件、止损/目标、仓位、理由和状态（待触发 / 观察 / 已买入 / 已放弃）。
- **记录** — 分析记录（评级、目标、止损、token、耗时、报告目录）+ 交易日志。

侧边栏底部（设置旁）还有一行常驻摘要：宽栏显示「图标 + 交易台 + 浮动盈亏%」，窄轨只留图标，悬停显示持仓数、浮动盈亏、今日盈亏、现金；点击直接切到主面板。数字由面板的每次加载/写入实时推送，另有 90 秒兜底轮询（页面隐藏时不请求）。

## Agent 工具

- `trading_desk_read` — `view`: `overview` / `positions` / `strategies` / `watchlist` / `records` / `journal` / `decision`。
- `trading_desk_write` — `action`: `upsert_position` / `remove_position` / `set_cash` / `add_note` / `save_plan` / `save_watchlist` / `delete_journal`。

面板与工具走同一个 Host 数据层：面板经 `/api/trading-desk` 路由调用，工具直接调用同一组方法，不各写一套规则。

## 配置

`cordis.patch.yml` 里的 `config`：

```yaml
workspaceRoot: ''   # 留空则自动寻找包含 data/logs 或 data/memory 的工作区
currency: CNY
```

## 自检

```powershell
node .dsh-plugins/trading-desk/scripts/selftest.mjs
```

打印工作区识别结果、价格解析、分析记录条数与聚合策略，用来确认解析没有回归。
