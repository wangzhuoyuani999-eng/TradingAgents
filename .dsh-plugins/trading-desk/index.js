/**
 * Host half of the Trading Desk bundle.
 *
 * One data path for both callers: the panel loads and mutates the book through
 * the `/api/trading-desk` route, and the two agent tools call the same
 * `applyRequest`. Nothing is computed twice and no view decides its own rules.
 */

import {
  applyRequest,
  buildSnapshot,
  resolveRoot,
} from './lib/data.js';

export const name = 'trading-desk';
export const inject = ['connection'];

const RPC_CHANNEL = '/trading-desk';
const RPC_PATH = `/api${RPC_CHANNEL}`;

/* ------------------------------------------------------------------- rpc */

function jsonReply(rpcId, result) {
  const value = result.ok === false
    ? { ...result, error: { ...result.error, details: result.error?.details ?? {} } }
    : result;
  return Response.json({ type: 'server-response', rpcId, result: value });
}

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * Mount the panel route. DSH authenticates the browser and applies its Host and
 * Origin checks before this handler runs, so only the envelope is validated here.
 */
function registerRoute(ctx, run) {
  return ctx.connection.fetch.register({
    path: RPC_PATH,
    methods: ['POST'],
    requestBody: 'buffered',
    async fetch(request) {
      if (request.method !== 'POST') return new Response('method not allowed', { status: 405 });
      const contentType = request.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase();
      if (contentType !== 'application/json') {
        return new Response('content type must be application/json', { status: 415 });
      }
      let message;
      try {
        message = await request.json();
      } catch {
        return new Response('body is not JSON', { status: 400 });
      }
      const rpcId = typeof message?.rpcId === 'string' ? message.rpcId : 'invalid-request';
      const call = message?.payload;
      if (!isRecord(message) || message.type !== 'client-request' || typeof message.rpcId !== 'string'
        || message.method !== 'trading-desk' || !isRecord(call) || typeof call.method !== 'string') {
        return jsonReply(rpcId, {
          ok: false,
          error: { code: 'gateway/bad-request', message: 'Invalid trading desk request.' },
        });
      }
      try {
        return jsonReply(rpcId, await run(call.method, call.payload, request.signal));
      } catch (error) {
        return jsonReply(rpcId, {
          ok: false,
          error: { code: 'trading-desk/failed', message: error?.message ?? 'Trading desk request failed.' },
        });
      }
    },
  });
}

/* ----------------------------------------------------------------- tools */

const money = (value, currency) => (value === null || value === undefined
  ? '—'
  : `${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}${currency ? ` ${currency}` : ''}`);

const signed = (value, currency) => {
  if (value === null || value === undefined) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${money(value, currency)}`;
};

const percent = (value) => (value === null || value === undefined ? '—' : `${value > 0 ? '+' : ''}${value}%`);

function priceLine(holding, currency) {
  const price = holding.last === null
    ? `成本价 ${money(holding.averagePrice, '')}`
    : `${money(holding.last, '')}${holding.priceSource === 'manual'
      ? `（手动价${holding.priceAsOf ? ` ${holding.priceAsOf}` : ''}）`
      : ''}`;
  return `- ${holding.ticker} ${holding.name} ${holding.quantity} 股 @${money(holding.averagePrice, '')} → ${price}`
    + ` · 市值 ${money(holding.marketValue, currency)}`
    + ` · 盈亏 ${signed(holding.pnl, currency)} (${percent(holding.pnlPct)})`
    + ` · 占比 ${holding.weight === null ? '—' : `${holding.weight}%`}`;
}

function overviewText(snapshot) {
  const { totals, currency } = snapshot;
  const lines = [
    `交易台快照 · ${new Date(snapshot.generatedAt).toLocaleString('zh-CN')}`,
    `工作区: ${snapshot.root}`,
    `持仓 ${totals.count} 只 · 市值 ${money(totals.marketValue, currency)} · 成本 ${money(totals.cost, currency)}`
      + ` · 浮动盈亏 ${signed(totals.pnl, currency)} (${percent(totals.pnlPct)})`
      + ` · 今日 ${signed(totals.dayPnl, currency)}`,
    `现金 ${money(totals.cash, currency)} · 总权益 ${money(totals.equity, currency)}`
      + ` · 仓位 ${totals.exposure === null ? '—' : `${totals.exposure}%`}`,
  ];
  if (snapshot.holdings.length > 0) {
    lines.push('持仓明细:', ...snapshot.holdings.map((holding) => priceLine(holding, currency)));
  } else {
    lines.push('当前没有登记持仓。');
  }
  const today = snapshot.strategies.find((day) => day.date === snapshot.today);
  if (today) {
    lines.push(`今日策略 (${today.date}):`);
    for (const item of today.items) {
      lines.push(`- ${item.ticker} 评级 ${item.rating ?? '—'} · 交易 ${item.action ?? '—'}`
        + ` · 入场 ${item.entryPrice ?? '—'} · 止损 ${item.stopLoss ?? '—'} · 目标 ${item.priceTarget ?? '—'}`);
    }
    if (today.plan) lines.push(`我的计划: ${today.plan.body}`);
  }
  if (snapshot.warnings.length > 0) lines.push('提示:', ...snapshot.warnings.map((warning) => `- ${warning}`));
  return lines.join('\n');
}

function strategiesText(snapshot) {
  const lines = [`每日策略 (${snapshot.strategies.length} 天)`];
  for (const day of snapshot.strategies.slice(0, 10)) {
    lines.push(`${day.date}${day.plan ? ` · 我的计划: ${day.plan.body}` : ''}`);
    for (const item of day.items) {
      lines.push(`  - ${item.ticker} 评级 ${item.rating ?? '—'} · 交易 ${item.action ?? '—'}`
        + ` · 入场 ${item.entryPrice ?? '—'} · 止损 ${item.stopLoss ?? '—'} · 目标 ${item.priceTarget ?? '—'}`
        + `${item.summary ? `\n    ${item.summary}` : ''}`);
    }
  }
  if (snapshot.strategies.length === 0) lines.push('还没有分析记录生成的策略。');
  return lines.join('\n');
}

function recordsText(snapshot, limit) {
  const lines = [`分析记录 (最近 ${Math.min(limit, snapshot.records.length)} / ${snapshot.records.length} 次)`];
  for (const record of snapshot.records.slice(0, limit)) {
    lines.push(`${record.date} ${record.ticker} · 评级 ${record.rating ?? '—'} · 交易 ${record.action ?? '—'}`
      + ` · 目标 ${record.priceTarget ?? '—'} · 止损 ${record.stopLoss ?? '—'}`
      + ` · ${record.metrics?.totalTokens ? `${record.metrics.totalTokens} tokens` : '无运行统计'}`);
    if (record.summary) lines.push(`  ${record.summary}`);
  }
  return lines.join('\n');
}

function journalText(snapshot) {
  if (snapshot.journal.length === 0) return '还没有交易日志。';
  return ['交易日志:', ...snapshot.journal.map((entry) => (
    `- ${entry.date} [${entry.kind === 'strategy' ? '计划' : '记录'}]${entry.ticker ? ` ${entry.ticker}` : ''}`
    + ` ${entry.title ? `${entry.title}: ` : ''}${entry.body}`
  ))].join('\n');
}

function watchlistText(snapshot) {
  const watchlist = snapshot.watchlist ?? { items: [] };
  if (!watchlist.items || watchlist.items.length === 0) return '候选池为空（data/trading_desk/watchlist.json）。';
  const lines = [`候选池 · ${watchlist.date || '未定日期'}（更新 ${watchlist.updatedAt ?? '—'}）`];
  if (watchlist.note) lines.push(watchlist.note);
  for (const item of watchlist.items) {
    const band = item.buyLow === null
      ? '—'
      : `${item.buyLow}${item.buyHigh === null || item.buyHigh === item.buyLow ? '' : `–${item.buyHigh}`}`;
    lines.push(`- ${item.ticker} ${item.name} · 买价 ${band} · 止损 ${item.stopLoss ?? '—'} · 目标 ${item.target ?? '—'}`
      + `${item.size ? ` · ${item.size}` : ''} · ${item.status}`);
    if (item.condition) lines.push(`  条件: ${item.condition}`);
    if (item.reason) lines.push(`  理由: ${item.reason}`);
  }
  return lines.join('\n');
}

function decisionText(record) {
  if (!record) return '没有找到匹配的分析记录。';
  return [
    `${record.date} ${record.ticker} · ${record.path}`,
    `评级 ${record.rating ?? '—'} · 交易 ${record.action ?? '—'} · 目标 ${record.priceTarget ?? '—'}`
      + ` · 入场 ${record.entryPrice ?? '—'} · 止损 ${record.stopLoss ?? '—'} · 周期 ${record.horizon ?? '—'}`,
    record.summary ? `概要: ${record.summary}` : '',
    record.reasoning ? `交易理由: ${record.reasoning}` : '',
  ].filter(Boolean).join('\n');
}

function readView(args, snapshot) {
  const view = typeof args?.view === 'string' ? args.view : 'overview';
  const limit = Number.isFinite(args?.limit) ? Math.max(1, Math.min(40, Math.trunc(args.limit))) : 10;
  switch (view) {
    case 'positions':
      return {
        data: {
          currency: snapshot.currency,
          cash: snapshot.book.cash,
          totals: snapshot.totals,
          holdings: snapshot.holdings,
        },
        text: overviewText(snapshot),
      };
    case 'strategies':
      return { data: { strategies: snapshot.strategies }, text: strategiesText(snapshot) };
    case 'watchlist':
      return { data: { watchlist: snapshot.watchlist }, text: watchlistText(snapshot) };
    case 'records':
      return { data: { records: snapshot.records.slice(0, limit) }, text: recordsText(snapshot, limit) };
    case 'journal':
      return { data: { journal: snapshot.journal }, text: journalText(snapshot) };
    case 'decision': {
      const ticker = typeof args?.ticker === 'string' ? args.ticker.trim().toUpperCase() : '';
      const date = typeof args?.date === 'string' ? args.date.trim() : '';
      const matches = snapshot.records.filter((record) => (
        (!ticker || record.ticker === ticker) && (!date || record.date === date)
      ));
      const record = matches[0] ?? null;
      return { data: { record, matches: matches.length }, text: decisionText(record) };
    }
    default:
      return {
        data: {
          today: snapshot.today,
          currency: snapshot.currency,
          totals: snapshot.totals,
          holdings: snapshot.holdings,
          todayStrategy: snapshot.strategies.find((day) => day.date === snapshot.today) ?? null,
          warnings: snapshot.warnings,
        },
        text: overviewText(snapshot),
      };
  }
}

const TEXT_BLOCK = (text) => [{ type: 'text', text }];

function readTool(ctx, config) {
  return {
    name: 'trading_desk_read',
    description: 'Read the reader\'s trading desk: current holdings with live profit and loss, the daily '
      + 'strategy produced by recent TradingAgents runs, past analysis records (rating, target, stop loss, '
      + 'token cost) and the trading journal. Call this before answering portfolio questions or proposing '
      + 'position sizes.',
    parameters: {
      type: 'object',
      properties: {
        view: {
          type: 'string',
          enum: ['overview', 'positions', 'strategies', 'watchlist', 'records', 'journal', 'decision'],
          description: 'overview: totals plus today\'s strategy. positions: holdings and cash. strategies: '
            + 'one entry per analysis date with the reader\'s own plan. watchlist: the day\'s candidates with '
            + 'buy band, trigger, stop, target and reasoning. records: recent report runs. '
            + 'journal: notes and plans the reader wrote. decision: one record, filtered by ticker/date.',
        },
        ticker: { type: 'string', description: 'Symbol filter for view=decision, e.g. 600036.SS.' },
        date: { type: 'string', description: 'Analysis date filter (YYYY-MM-DD) for view=decision.' },
        limit: { type: 'number', description: 'How many recent records to return, 1-40. Default 10.' },
      },
      required: ['view'],
      additionalProperties: false,
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render(args, value) {
        return TEXT_BLOCK(typeof value?.text === 'string' ? value.text : JSON.stringify(value, null, 2));
      },
    },
    async execute(args) {
      const root = resolveRoot(ctx, config);
      const { data, text } = readView(args, buildSnapshot(root, config));
      return { ...data, text };
    },
  };
}

function writeTool(ctx, config) {
  return {
    name: 'trading_desk_write',
    description: 'Update the reader\'s trading desk: add or change a holding, remove a holding, set free '
      + 'cash, or write a daily note/plan. Every write goes through the same store the panel uses; the '
      + 'TradingAgents CLI portfolio file is rewritten so the next analysis run sizes against this book.',
    parameters: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['upsert_position', 'remove_position', 'set_cash', 'add_note', 'save_plan', 'delete_journal',
            'save_watchlist'],
          description: 'upsert_position: create or overwrite one holding. remove_position: drop it. '
            + 'set_cash: free cash and currency. add_note: journal note. save_plan: replace the plan of one '
            + 'date. save_watchlist: replace the day\'s candidate pool. delete_journal: remove a journal entry by id.',
        },
        ticker: { type: 'string', description: 'Instrument symbol, e.g. 600036.SS or NVDA.' },
        name: { type: 'string', description: 'Display name; defaults to the ticker.' },
        quantity: { type: 'number', description: 'Units held; negative is short. Required by upsert_position.' },
        averagePrice: { type: 'number', description: 'Average entry price per unit.' },
        stopLoss: { type: 'number', description: 'Stop price the reader is honouring.' },
        targetPrice: { type: 'number', description: 'The reader\'s own target price.' },
        manualPrice: {
          type: 'number',
          description: 'Quote for an asset with no market-data feed (open-end fund, wealth product). '
            + 'Used when the workspace has no price cache for the symbol; stamped with today\'s date.',
        },
        note: { type: 'string', description: 'Free note stored on the position.' },
        cash: { type: 'number', description: 'Free cash, for set_cash.' },
        currency: { type: 'string', description: 'Currency label such as CNY or USD.' },
        date: { type: 'string', description: 'Journal date YYYY-MM-DD; defaults to today.' },
        title: { type: 'string', description: 'Journal title.' },
        body: { type: 'string', description: 'Journal or plan text.' },
        id: { type: 'string', description: 'Journal entry id, for delete_journal.' },
        items: {
          type: 'array',
          description: 'Candidate list for save_watchlist. Each item: ticker, name, priority, buyLow, buyHigh, '
            + 'condition, stopLoss, target, size, reason, status.',
          items: { type: 'object', additionalProperties: true },
        },
      },
      required: ['action'],
      additionalProperties: false,
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render(args, value) {
        return TEXT_BLOCK(typeof value?.text === 'string' ? value.text : JSON.stringify(value, null, 2));
      },
    },
    async execute(args) {
      const root = resolveRoot(ctx, config);
      const action = typeof args?.action === 'string' ? args.action : '';
      let result;
      switch (action) {
        case 'upsert_position':
          result = await applyRequest(root, config, 'upsertPosition', {
            ticker: args.ticker,
            name: args.name,
            quantity: args.quantity,
            averagePrice: args.averagePrice,
            stopLoss: args.stopLoss,
            targetPrice: args.targetPrice,
            manualPrice: args.manualPrice,
            note: args.note,
          });
          break;
        case 'remove_position':
          result = await applyRequest(root, config, 'removePosition', { ticker: args.ticker });
          break;
        case 'set_cash':
          result = await applyRequest(root, config, 'setCash', { cash: args.cash, currency: args.currency });
          break;
        case 'add_note':
          result = await applyRequest(root, config, 'saveJournal', {
            date: args.date, kind: 'note', title: args.title, body: args.body, ticker: args.ticker,
          });
          break;
        case 'save_plan':
          result = await applyRequest(root, config, 'saveJournal', {
            date: args.date, kind: 'strategy', title: args.title, body: args.body,
          });
          break;
        case 'delete_journal':
          result = await applyRequest(root, config, 'deleteJournal', { id: args.id });
          break;
        case 'save_watchlist':
          result = await applyRequest(root, config, 'saveWatchlist', {
            date: args.date, note: args.note, items: args.items,
          });
          break;
        default:
          throw new Error(`未知操作 ${action || '(empty)'}`);
      }
      if (result.ok !== true) throw new Error(result.error?.message ?? '写入失败');
      const next = result.value;
      const label = {
        upsert_position: `已保存 ${String(args.ticker ?? '').toUpperCase()}`,
        remove_position: `已移除 ${String(args.ticker ?? '').toUpperCase()}`,
        set_cash: `现金已设为 ${money(next.totals.cash, next.currency)}`,
        add_note: '已写入交易日志',
        save_plan: `已保存 ${next.today} 的交易计划`,
        save_watchlist: `已保存候选池（${next.watchlist?.items?.length ?? 0} 只）`,
        delete_journal: '已删除日志条目',
      }[action];
      return {
        ok: true,
        message: label,
        totals: next.totals,
        currency: next.currency,
        text: `${label}\n${overviewText(next)}`,
      };
    },
    isConcurrencySafe() {
      return false;
    },
  };
}

/* ------------------------------------------------------------------ apply */

export function apply(ctx, config = {}) {
  const settings = {
    workspaceRoot: typeof config?.workspaceRoot === 'string' ? config.workspaceRoot : '',
    currency: typeof config?.currency === 'string' && config.currency ? config.currency : 'CNY',
  };

  const run = (method, payload, signal) => {
    if (signal?.aborted) {
      return { ok: false, error: { code: 'cancelled', message: '请求已取消。' } };
    }
    return applyRequest(resolveRoot(ctx, settings), settings, method, payload);
  };

  ctx.effect(() => registerRoute(ctx, run), 'trading desk: panel route');

  const installTools = (toolCtx) => {
    toolCtx.effect(() => {
      const stopRead = toolCtx.tools.register(readTool(ctx, settings));
      const stopWrite = toolCtx.tools.register(writeTool(ctx, settings));
      return () => {
        stopRead();
        stopWrite();
      };
    }, 'trading desk: agent tools');
  };
  if (typeof ctx.inject === 'function') {
    ctx.effect(() => ctx.inject(['tools'], installTools), 'trading desk: tool service');
  } else if (typeof ctx.get === 'function' && ctx.get('tools')) {
    ctx.effect(() => installTools(ctx), 'trading desk: agent tools');
  }
}
