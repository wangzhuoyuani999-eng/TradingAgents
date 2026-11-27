# 数据源细节与已知坑

每一条都是实际踩过、修过的问题。**遇到异常时先在这里找，不要重新排查。**

## 一、数据层（`data_sources.py`）

| 用途 | 源 | 说明 |
|---|---|---|
| 全市场列表 | 新浪 | 约 5,220 只；`mktcap`/`nmc` 单位是**万元**，要 ×1e4 |
| 前复权日线 | 腾讯 | `qfq`，成交量单位是**手** → `amount = volume × 100 × close` |
| 实时报价 | 腾讯 | `quote(codes)`，返回 `px/pct/high/low` |
| 指数 | 腾讯 | **必须传 `index=True`**，见坑 #4 |

**所有请求都 `Session.trust_env=False`（直连，不走代理）。**
只有东财 F10（基本面）需要代理。

## 二、踩过的坑

### #1 腾讯 K 线接口 501

`web.ifzq.gtimg.cn` 被高频调用后返回 **501**。
**解法**：优先 `proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get`，
失败再退回 `web.ifzq.gtimg.cn`，并加 `time.sleep(0.03)`。

### #2 日线滞后一天（**最容易漏，会算错趋势分**）

腾讯/新浪的日线在收盘后一段时间**仍停留在前一交易日**。
后果：当天刚创出的新高被漏掉，趋势模板、MA20、买区全部基于旧数据。

**解法**：`screen_v3.py` 的 `kline()` 里，若日线最后日期 < 今天，就用**实时价补一根当日 bar**：

```python
bar = {"date": today, "open": px, "close": px,
       "high": max(high, px), "low": min(low, px), "volume": nan}
```

修好后候选数从 1 只变 2 只——**说明这个坑确实在吞标的**。

### #3 东财 F10 限流返回空 → 被当成"无数据放行"

原逻辑把 `yoy_net` 为 NaN 当成"缺数据，放行"，导致**6 只没有财务数据的票**（银行、电力等）
混进候选池，还都显示"基本面分 0.0"。

**解法**：
1. `f10_growth()` 加 **3 次重试 + 退避**（0.8s/1.6s/2.4s）
2. 硬门槛改为 **`has_data & (yoy_net ≥ 20) & (yoy_rev ≥ 10)`** —— 无数据**直接剔除**
3. 日志单独打印"另 N 只无财务数据，已剔除"

修好后候选从 8 只缩到 2 只。

### #4 `quote(["000001"])` 返回平安银行

`000001` 既是上证指数代码，也是平安银行代码。默认返回个股。

**解法**：`ds.quote(["000001"], index=True)`。指数映射表 `INDEX_SYMBOLS`：
`000001`→`sh000001`、`399001`→`sz399001`、`399006`→`sz399006`。

### #5 新浪未复权数据把回测吹成 +620%

用新浪原始价做长期回测，除权缺口被当成下跌，收益虚高。
**解法**：回测一律用 `ds.kline_qfq()`（腾讯前复权）。修正后真实值 **+193.8%**。

### #6 腾讯 `web.ifzq` 并发被限

串行拉 400 只时偶发整批失败。
**解法**：控制并发（`time.sleep`），并接受"单只取不到就跳过"——**不要因为一只票失败而中断整轮**。

### #7 `run.cmd` 返回 exit code 1 但实际成功

`cli_prefs.json` 权限写入失败导致退出码非零，**报告照常生成**。
判断成功与否看 `data/logs/reports/` 下是否出现新目录 + `complete_report.md`。

### #8 面板"今日盈亏"与实际不符

`lib/data.js` 用缓存价算当日涨跌，缓存未更新当日 K 线时会显示 0 或旧值。
**解法**：收盘后手动把当日收盘补进 `data/cache/<TICKER>-YFin-data.csv`
（`Date/Open/High/Low/Close/Volume` 六列，日期格式 `YYYY-MM-DD 00:00:00+08:00`）。

### #9 yfinance 给 A 股返回自相矛盾的 K 线（TradingAgents 侧）

**现象**：2026-11-18 的 `002415.SZ` 从 yfinance 拿到
`Open 33.75 / High 35.59 / Low 35.08 / Close 35.29` —— **开盘价低于当日最低价**，
物理上不可能（33.75 恰好等于 11-13 的开盘价，像是索引错位）。
LLM 尽调报告直接指出这点，并把当天的形态与量能信息作废。

**根因**：`data_vendors["core_stock_apis"]` 原来是 `yfinance`，A 股 OHLCV 也走雅虎。

**修法（已落地）**：
1. `default_config.py` → `core_stock_apis = "eastmoney,yfinance"`。
   东财对非 A 股会抛 `NoMarketDataError`，美股仍自动回退雅虎（已验证 AAPL 正常）。
2. `yahoo/ohlcv.py` 加 `_repair_impossible_bars()`：Open/Close 超出 [Low, High] 时
   夹进区间并打 warning（兜底，防止美股将来出现同类问题）。
3. 清掉缓存里被污染的 11-18 行。

**注意**：`get_indicators` 只有 `alpha_vantage` / `yfinance` 两家，**没有东财**，
所以技术指标仍走雅虎。但多数指标只用 Close/High/Low/Volume，**不用 Open**，
影响仅限形态/跳空类判断。

## 三、排错顺序

数据不对时按这个顺序查，别跳步：

```
1. 单只票能不能拉？（data_sources.quote(["600111"])）
   ├ 不能 → 网络/接口 → 换备用接口，直连不要走代理
   └ 能   → 下一步
2. 日线最后日期是今天吗？
   ├ 否 → 坑 #2，补当日 bar
   └ 是 → 下一步
3. 财务数据拿到了吗？（f10_growth）
   ├ 空 → 坑 #3，重试；仍空则该票本轮剔除
   └ 有 → 下一步
4. 板块过滤生效吗？（有没有 300/301/688/689）
   └ 有 → 报警，检查 stage0 的 assert
```

## 四、回测基线（改动策略后要对比的基准）

| 指标 | 值 |
|---|---|
| 区间 | 2024-03 → 2026-11 |
| 交易数 | 206 |
| 胜率 | 41.3% |
| 平均收益 | +3.94% |
| 盈亏比 PF | 1.92 |
| 累计收益 | +193.8% |
| 最大回撤 | −15.5% |
| 同期基准 | +153.8% |

**基本面分层（有前视偏差，仅作方向参考）**：
`yoy_net ≥ +20%` 组 胜率 43.7% / +4.92% / PF 2.18 —— 门槛是有效的。

**迭代纪律**：改动必须在同窗口回测上取得 **≥10% 的改善**才采纳；
评估节点为 20 笔成交 / 一个季度 / 连续 5 笔亏损。
详见 `research/策略迭代日志.md`。

## 五、LLM 通道

当前走三个通道之一，配置在 `.env`：

| 通道 | provider | 模型 | 备注 |
|---|---|---|---|
| 本地 Magpie 网关 | `magpie` | `opendesign/deepseek-v4.1-flash` | 默认，`http://127.0.0.1:3425/v1` |
| Open Design 云网关 | `open-design` | `deepseek-v4.1-flash` | 需 `OPENDESIGN_API_KEY` |
| DeepSeek 官方 | `deepseek` | `deepseek-flash` | 直连 |

**换模型只改 `.env` 三行**，代码不用动。
`deepseek-v4-pro` 更强但慢约 65%、token 少一半——适合关键决策前复核，不适合日常巡检。

## 六、盘前尽调（07:00）踩过的坑（2026-11-25）

| 症状 | 真因 | 处置 |
|---|---|---|
| `diligence.py` 跑 7 分钟后 `ok=false`，stderr 里是 `Polymarket search failed ... ConnectTimeout` | news 分析师的预测市场工具直连 Polymarket，国内网络不通，原来 30s 超时 ×N 把整轮拖死 | **已修（2026-11-25 晚）**：`polymarket.py` 改成 4s 快失败 + 进程内熔断（首个 topic 最多 ~8s，后续 0s），news 分析师**已恢复**（`--analysts market,news,fundamentals`）；消息面另有固化脚本 `tools/news_digest.py` |
| 探活两次都 `TimeoutError (20.0s)`，直接判「没有可用模型」 | 网关偶发 20s 抖动（实测同一时刻 `/v1/models` 与 `/chat/completions` 都正常，2s 返回） | `--no-probe` 跳过探活再跑一次；不要把一次探活超时当成网关挂了 |
| 分析成功但脚本崩：`ValueError: '...\.tradingagents\logs\600885.SS\2026-11-25' is not in the subpath of ...` | CLI 默认把报告写 `~/.tradingagents/logs`，脚本硬 `relative_to(ROOT)` | 已修：脚本默认 `TRADINGAGENTS_RESULTS_DIR=<repo>/data/logs/reports`，且 `_rel()` 兼容仓库外路径；历史报告可手工拷进 `data/logs/reports/<TICKER>_<日期>_<时间>` |
| 尽调还没跑完就先把「等回踩买入」推去飞书，结果几分钟后被 Underweight 打脸 | 流程顺序错：结论要等尽调回来再写/再推 | **先把尽调跑完拿到评级，再写 PORTFOLIO.md、再重建面板、再推送**；已推错的要补一条「更正」 |
