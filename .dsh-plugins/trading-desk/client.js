/**
 * Client half of the Trading Desk bundle.
 *
 * The panel renders inside the Harness shell through `main` and
 * `sidebar.panellist`. Every number arrives from the Host route already folded,
 * so the component only formats, sorts and renders.
 */
window.__ModuleLoader__.load({
  id: '@local/dsh-trading-desk',
  factory(require) {
    const React = require('react');
    const h = React.createElement;

    const PANEL_ID = 'trading-desk';
    const RPC_CHANNEL = 'trading-desk';

    /* ------------------------------------------------------------ locale */

    const DICT = {
      title: ['交易台', 'Trading Desk'],
      subtitle: ['持仓 · 盈亏 · 分析记录 · 每日策略', 'Holdings, P&L, analysis records and daily strategy'],
      tabOverview: ['总览', 'Overview'],
      tabPositions: ['持仓', 'Holdings'],
      tabStrategies: ['策略', 'Strategy'],
      tabWatchlist: ['候选', 'Watchlist'],
      tabRecords: ['记录', 'Records'],
      refresh: ['刷新', 'Refresh'],
      loading: ['正在读取交易台…', 'Loading the trading desk…'],
      retry: ['重试', 'Retry'],
      emptyHoldings: ['还没有登记持仓。', 'No holdings recorded yet.'],
      emptyHoldingsHint: [
        '添加一只标的，或从最近的 13 次分析里挑一个。',
        'Add an instrument, or pick one of the recent analyses.',
      ],
      marketValue: ['总市值', 'Market value'],
      floatPnl: ['浮动盈亏', 'Unrealized P&L'],
      dayPnl: ['今日盈亏', "Today's P&L"],
      cash: ['现金', 'Cash'],
      equity: ['总权益', 'Equity'],
      exposure: ['仓位', 'Exposure'],
      positions: ['持仓', 'Positions'],
      priced: ['已有价格', 'Priced'],
      cost: ['成本', 'Cost'],
      weightOf: ['占比', 'Weight'],
      ticker: ['代码', 'Symbol'],
      name: ['名称', 'Name'],
      quantity: ['数量', 'Qty'],
      avgPrice: ['成本价', 'Avg price'],
      lastPrice: ['现价', 'Last'],
      pnl: ['盈亏', 'P&L'],
      actions: ['操作', 'Actions'],
      edit: ['编辑', 'Edit'],
      remove: ['移除', 'Remove'],
      addPosition: ['新增持仓', 'Add holding'],
      save: ['保存', 'Save'],
      cancel: ['取消', 'Cancel'],
      stopLoss: ['止损', 'Stop'],
      target: ['目标', 'Target'],
      note: ['备注', 'Note'],
      cashEditor: ['现金与币种', 'Cash and currency'],
      currency: ['币种', 'Currency'],
      todayStrategy: ['今日策略', "Today's strategy"],
      noStrategyToday: ['今天还没有分析记录。', 'No analysis for today yet.'],
      myPlan: ['我的计划', 'My plan'],
      writePlan: ['写今日计划', "Write today's plan"],
      editPlan: ['编辑计划', 'Edit plan'],
      planPlaceholder: ['今天的执行计划、加减仓条件、风控纪律…', 'Execution plan, add/trim conditions, risk rules…'],
      strategies: ['每日策略', 'Daily strategy'],
      noStrategies: ['还没有分析记录生成的策略。', 'No strategy from analysis runs yet.'],
      watchlist: ['候选池', 'Watchlist'],
      noWatchlist: ['候选池是空的。', 'The watchlist is empty.'],
      noWatchlistHint: [
        '让 Agent 写入当天的候选：买价区间、触发条件、止损、目标与理由。',
        'Ask the agent to write the day\'s candidates: buy band, trigger, stop, target and reason.',
      ],
      buyBand: ['买价', 'Buy'],
      condition: ['条件', 'Trigger'],
      reason: ['理由', 'Why'],
      sizeLabel: ['仓位', 'Size'],
      status: ['状态', 'Status'],
      conditionReason: ['条件 / 理由', 'Trigger / why'],
      records: ['分析记录', 'Analysis records'],
      noRecords: ['还没有分析记录。', 'No analysis records yet.'],
      rating: ['评级', 'Rating'],
      action: ['交易', 'Action'],
      runs: ['次分析', 'runs'],
      journal: ['交易日志', 'Journal'],
      noJournal: ['还没有日志。', 'No journal entries yet.'],
      addNote: ['写一条记录', 'Add a note'],
      noteTitle: ['标题', 'Title'],
      noteBody: ['内容', 'Content'],
      delete: ['删除', 'Delete'],
      generatedAt: ['更新于', 'Updated'],
      workspace: ['工作区', 'Workspace'],
      detected: ['已识别 TradingAgents 工作区', 'TradingAgents workspace detected'],
      notDetected: ['未识别到 TradingAgents 工作区，请检查配置', 'TradingAgents workspace not found; check config'],
      journalKindNote: ['记录', 'Note'],
      journalKindStrategy: ['计划', 'Plan'],
      saving: ['保存中…', 'Saving…'],
      failed: ['操作失败', 'Operation failed'],
      warnings: ['提示', 'Notes'],
      noPrice: ['无价格缓存', 'No price cache'],
      manualPrice: ['手动价格', 'Manual price'],
      manualTag: ['手动', 'manual'],
      priceHint: [
        '没有行情缓存的标的（场外基金、理财）用这一项填报价；留空则按成本价估值。',
        'Give a quote here for assets with no market feed (open-end funds, wealth products); empty falls back to cost.',
      ],
      asOf: ['截至', 'as of'],
      tokens: ['tokens', 'tokens'],
      openReport: ['报告目录', 'Report folder'],
      quickAdd: ['从分析过的标的快速添加', 'Quick add an analysed symbol'],
      symbolRequired: ['请先填写标的代码。', 'Enter a symbol first.'],
    };

    function makeT(tag) {
      const zh = String(tag || '').toLowerCase().startsWith('zh');
      return (key) => {
        const entry = DICT[key];
        if (!entry) return key;
        return zh ? entry[0] : entry[1];
      };
    }

    function useTranslator(ctx) {
      const subscribe = React.useCallback((notify) => (
        typeof ctx.on === 'function' ? ctx.on('locale/change', notify) : () => {}
      ), [ctx]);
      const read = React.useCallback(() => ctx.locale?.getLocale?.()?.active ?? '', [ctx]);
      const tag = React.useSyncExternalStore(subscribe, read, read);
      return React.useMemo(() => makeT(tag), [tag]);
    }

    /* ------------------------------------------------------------ styles */

    const CSS = `
.td-page { display: flex; flex-direction: column; height: 100%; min-height: 0; background: var(--dsw-alias-bg-base); color: var(--dsw-alias-label-primary); }
.td-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 20px 24px 12px; }
.td-title { font-size: 18px; font-weight: 600; letter-spacing: 0.2px; }
.td-sub { margin-top: 4px; font-size: 12px; color: var(--dsw-alias-label-secondary); word-break: break-all; }
.td-head-actions { display: flex; align-items: center; gap: 8px; flex: none; }
.td-pill { font-size: 12px; color: var(--dsw-alias-label-secondary); border: 1px solid var(--dsw-alias-border-l1); border-radius: 999px; padding: 4px 10px; white-space: nowrap; }
.td-btn { appearance: none; border: 1px solid var(--dsw-alias-border-l1); background: var(--dsw-alias-bg-layer-1); color: var(--dsw-alias-label-primary); border-radius: 8px; padding: 6px 12px; font-size: 12px; cursor: pointer; font-family: inherit; transition: background 120ms ease, border-color 120ms ease; }
.td-btn:hover { background: var(--dsw-alias-bg-layer-2); border-color: var(--dsw-alias-border-l2); }
.td-btn:disabled { opacity: 0.55; cursor: default; }
.td-btn-primary { background: var(--dsw-alias-brand-primary); border-color: transparent; color: #fff; }
.td-btn-primary:hover { background: var(--dsw-alias-brand-primary); filter: brightness(1.06); }
.td-btn-ghost { background: transparent; }
.td-btn-danger { color: var(--dsw-alias-state-error-primary); }
.td-tabs { display: flex; gap: 4px; padding: 0 24px; border-bottom: 1px solid var(--dsw-alias-border-l1); }
.td-tab { appearance: none; border: none; background: transparent; color: var(--dsw-alias-label-secondary); font-size: 13px; padding: 10px 12px; cursor: pointer; font-family: inherit; border-bottom: 2px solid transparent; margin-bottom: -1px; }
.td-tab[data-active="true"] { color: var(--dsw-alias-label-primary); border-bottom-color: var(--dsw-alias-brand-primary); font-weight: 600; }
.td-body { flex: 1; min-height: 0; overflow: auto; padding: 16px 24px 32px; }
.td-split { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.td-kpi { border: 1px solid var(--dsw-alias-border-l1); border-radius: 12px; background: var(--dsw-alias-bg-layer-1); padding: 12px 14px; }
.td-kpi-label { font-size: 11px; color: var(--dsw-alias-label-secondary); letter-spacing: 0.3px; }
.td-kpi-value { margin-top: 6px; font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums; letter-spacing: -0.2px; }
.td-kpi-sub { margin-top: 2px; font-size: 11px; color: var(--dsw-alias-label-secondary); font-variant-numeric: tabular-nums; }
.td-card { border: 1px solid var(--dsw-alias-border-l1); border-radius: 12px; background: var(--dsw-alias-bg-layer-1); padding: 14px 16px; margin-top: 14px; }
.td-card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.td-card-title { font-size: 13px; font-weight: 600; }
.td-up { color: var(--dsw-alias-state-success-primary); }
.td-down { color: var(--dsw-alias-state-error-primary); }
.td-muted { color: var(--dsw-alias-label-secondary); }
.td-mono { font-variant-numeric: tabular-nums; }
.td-table-wrap { overflow-x: auto; margin-top: 10px; }
.td-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.td-table th { text-align: right; font-weight: 500; font-size: 11px; color: var(--dsw-alias-label-secondary); padding: 6px 10px; border-bottom: 1px solid var(--dsw-alias-border-l1); white-space: nowrap; }
.td-table th:first-child, .td-table th:nth-child(2) { text-align: left; }
.td-table td { text-align: right; padding: 9px 10px; border-bottom: 1px solid var(--dsw-alias-border-l1); font-variant-numeric: tabular-nums; white-space: nowrap; }
.td-table td:first-child, .td-table td:nth-child(2) { text-align: left; white-space: normal; }
.td-table tbody tr:hover { background: var(--dsw-alias-bg-layer-2); }
.td-table tbody tr:last-child td { border-bottom: none; }
.td-symbol { font-weight: 600; }
.td-name { color: var(--dsw-alias-label-secondary); font-size: 11.5px; }
.td-badge { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--dsw-alias-border-l1); color: var(--dsw-alias-label-secondary); }
.td-badge[data-tone="buy"] { color: var(--dsw-alias-state-success-primary); border-color: color-mix(in srgb, var(--dsw-alias-state-success-primary) 45%, transparent); }
.td-badge[data-tone="sell"] { color: var(--dsw-alias-state-error-primary); border-color: color-mix(in srgb, var(--dsw-alias-state-error-primary) 45%, transparent); }
.td-badge[data-tone="hold"] { color: var(--dsw-alias-state-warn-primary); border-color: color-mix(in srgb, var(--dsw-alias-state-warn-primary) 45%, transparent); }
.td-rows { display: flex; flex-direction: column; gap: 8px; }
.td-row { display: grid; grid-template-columns: 120px 1fr 90px; align-items: center; gap: 12px; font-size: 12.5px; }
.td-bar { height: 6px; border-radius: 999px; background: var(--dsw-alias-bg-layer-2); overflow: hidden; }
.td-bar > span { display: block; height: 100%; border-radius: 999px; background: var(--dsw-alias-brand-primary); }
.td-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-top: 10px; }
.td-field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.td-field > span { font-size: 11px; color: var(--dsw-alias-label-secondary); }
.td-input, .td-textarea, .td-select { width: 100%; box-sizing: border-box; font-family: inherit; font-size: 12.5px; color: var(--dsw-alias-label-primary); background: var(--dsw-alias-bg-base); border: 1px solid var(--dsw-alias-border-l1); border-radius: 8px; padding: 7px 9px; outline: none; }
.td-input:focus, .td-textarea:focus, .td-select:focus { border-color: var(--dsw-alias-brand-primary); }
.td-textarea { min-height: 78px; resize: vertical; line-height: 1.6; }
.td-form-actions { display: flex; gap: 8px; justify-content: flex-end; grid-column: 1 / -1; }
.td-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.td-chip { appearance: none; font-family: inherit; font-size: 11.5px; border: 1px dashed var(--dsw-alias-border-l2); background: transparent; color: var(--dsw-alias-label-secondary); border-radius: 999px; padding: 3px 10px; cursor: pointer; }
.td-chip:hover { color: var(--dsw-alias-label-primary); border-style: solid; }
.td-empty { border: 1px dashed var(--dsw-alias-border-l1); border-radius: 12px; padding: 26px 18px; text-align: center; color: var(--dsw-alias-label-secondary); font-size: 13px; }
.td-empty strong { display: block; color: var(--dsw-alias-label-primary); font-size: 14px; margin-bottom: 6px; }
.td-empty-hint { font-size: 12px; margin-top: 6px; }
.td-error { border: 1px solid var(--dsw-alias-state-error-primary); color: var(--dsw-alias-state-error-primary); background: var(--dsw-alias-bg-layer-1); border-radius: 10px; padding: 10px 12px; font-size: 12.5px; margin-bottom: 12px; }
.td-warn { border: 1px solid var(--dsw-alias-state-warn-primary); color: var(--dsw-alias-state-warn-primary); border-radius: 10px; padding: 8px 12px; font-size: 12px; margin-top: 12px; }
.td-day { border: 1px solid var(--dsw-alias-border-l1); border-radius: 12px; background: var(--dsw-alias-bg-layer-1); padding: 12px 16px; margin-bottom: 10px; }
.td-day-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.td-day-date { font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; }
.td-item { display: grid; grid-template-columns: 110px auto 1fr; gap: 10px; align-items: start; padding: 9px 0; border-top: 1px solid var(--dsw-alias-border-l1); margin-top: 8px; font-size: 12.5px; }
.td-item:first-of-type { border-top: none; }
.td-item-meta { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-size: 11.5px; color: var(--dsw-alias-label-secondary); }
.td-item-summary { font-size: 12px; color: var(--dsw-alias-label-secondary); line-height: 1.65; }
.td-plan { margin-top: 10px; border-top: 1px dashed var(--dsw-alias-border-l1); padding-top: 10px; }
.td-plan-label { font-size: 11px; color: var(--dsw-alias-label-secondary); margin-bottom: 4px; }
.td-plan-body { font-size: 12.5px; line-height: 1.7; white-space: pre-wrap; }
.td-record { border-top: 1px solid var(--dsw-alias-border-l1); padding: 10px 0; }
.td-record:first-child { border-top: none; padding-top: 0; }
.td-record-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 12.5px; }
.td-record-summary { margin-top: 6px; font-size: 12px; line-height: 1.7; color: var(--dsw-alias-label-secondary); }
.td-record-metrics { margin-top: 4px; font-size: 11px; color: var(--dsw-alias-label-secondary); font-variant-numeric: tabular-nums; }
.td-journal { border-top: 1px solid var(--dsw-alias-border-l1); padding: 9px 0; font-size: 12.5px; }
.td-journal:first-of-type { border-top: none; }
.td-journal-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.td-journal-body { margin-top: 4px; line-height: 1.7; white-space: pre-wrap; color: var(--dsw-alias-label-secondary); }
.td-spark { display: block; }
.td-loading { padding: 40px 0; text-align: center; color: var(--dsw-alias-label-secondary); font-size: 13px; }
.td-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; }
.td-toolbar-left { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 12px; color: var(--dsw-alias-label-secondary); }
.td-inline-form { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 8px; }
.td-inline-form .td-field { width: 120px; }
.td-foot { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; min-width: 0; height: 28px; padding: 0 8px; border: none; border-radius: 8px; background: transparent; color: var(--dsw-alias-label-secondary); font-family: inherit; font-size: 12px; cursor: pointer; transition: background 120ms ease, color 120ms ease; }
.td-foot:hover, .td-foot:focus-visible { background: var(--dsw-alias-bg-layer-2); color: var(--dsw-alias-label-primary); outline: none; }
.td-foot[data-wide="false"] { width: 28px; padding: 0; justify-content: center; }
.td-foot-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.td-foot-value { flex: none; font-variant-numeric: tabular-nums; font-weight: 600; }
.td-foot-dot { flex: none; width: 5px; height: 5px; border-radius: 999px; background: var(--dsw-alias-brand-primary); }
`;

    function Styles() {
      return h('style', { key: 'td-style' }, CSS);
    }

    /* ----------------------------------------------------------- format */

    const money = (value, currency) => {
      if (value === null || value === undefined || Number.isNaN(value)) return '—';
      const text = new Intl.NumberFormat('zh-CN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(value);
      return currency ? `${text} ${currency}` : text;
    };

    const compact = (value) => {
      if (value === null || value === undefined) return '—';
      const abs = Math.abs(value);
      if (abs >= 1e8) return `${(value / 1e8).toFixed(2)} 亿`;
      if (abs >= 1e4) return `${(value / 1e4).toFixed(2)} 万`;
      return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value);
    };

    const signed = (value, formatter) => {
      if (value === null || value === undefined) return '—';
      return `${value > 0 ? '+' : ''}${formatter(value)}`;
    };

    const pct = (value) => (value === null || value === undefined ? '—' : `${value > 0 ? '+' : ''}${value}%`);

    function toneOf(value) {
      if (value === null || value === undefined || value === 0) return '';
      return value > 0 ? 'td-up' : 'td-down';
    }

    function ratingTone(rating) {
      if (!rating) return 'hold';
      const text = String(rating).toLowerCase();
      if (text.startsWith('buy') || text.startsWith('over')) return 'buy';
      if (text.startsWith('sell') || text.startsWith('under')) return 'sell';
      return 'hold';
    }

    function Sparkline({ values, tone }) {
      if (!Array.isArray(values) || values.length < 2) return null;
      const width = 64;
      const height = 20;
      const min = Math.min(...values);
      const max = Math.max(...values);
      const span = max - min || 1;
      const points = values.map((value, index) => {
        const x = (index / (values.length - 1)) * width;
        const y = height - ((value - min) / span) * height;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      }).join(' ');
      const stroke = tone === 'down'
        ? 'var(--dsw-alias-state-error-primary)'
        : 'var(--dsw-alias-state-success-primary)';
      return h('svg', {
        className: 'td-spark',
        width,
        height,
        viewBox: `0 0 ${width} ${height}`,
        'aria-hidden': true,
      }, h('polyline', {
        points,
        fill: 'none',
        stroke,
        strokeWidth: 1.4,
        strokeLinecap: 'round',
        strokeLinejoin: 'round',
        opacity: 0.85,
      }));
    }

    /* -------------------------------------------------------- desk share */

    // The panel publishes every snapshot it loads or writes, so the sidebar row
    // renders the same numbers without a second request, and a write made in the
    // panel shows up in the sidebar immediately.
    let deskSnapshot = null;
    const deskListeners = new Set();

    function publishDesk(snapshot) {
      if (!snapshot) return;
      deskSnapshot = snapshot;
      for (const listener of deskListeners) {
        try {
          listener(snapshot);
        } catch {
          /* one broken row must not break the writer */
        }
      }
    }

    function subscribeDesk(listener) {
      deskListeners.add(listener);
      return () => {
        deskListeners.delete(listener);
      };
    }

    function deskTooltip(snapshot, t) {
      if (!snapshot) return t('title');
      const totals = snapshot.totals;
      const head = `${t('title')} · ${t('positions')} ${totals.count}`;
      if (totals.count === 0) return `${head} · ${t('emptyHoldings')}`;
      return `${head} · ${t('floatPnl')} ${signed(totals.pnl, (value) => money(value, snapshot.currency))}`
        + ` (${pct(totals.pnlPct)}) · ${t('dayPnl')} ${signed(totals.dayPnl, (value) => money(value))}`
        + ` · ${t('cash')} ${money(totals.cash)}`;
    }

    /* --------------------------------------------------------- fragments */

    function Kpi({ label, value, sub, tone }) {
      return h('div', { className: 'td-kpi' },
        h('div', { className: 'td-kpi-label' }, label),
        h('div', { className: `td-kpi-value ${tone || ''}` }, value),
        sub ? h('div', { className: 'td-kpi-sub' }, sub) : null);
    }

    function Empty({ title, hint }) {
      return h('div', { className: 'td-empty' },
        h('strong', null, title),
        hint ? h('div', { className: 'td-empty-hint' }, hint) : null);
    }

    /* ------------------------------------------------------------ panels */

    function OverviewTab({ snapshot, t, onOpenPositions }) {
      const { totals, currency } = snapshot;
      const today = snapshot.strategies.find((day) => day.date === snapshot.today);
      return h(React.Fragment, null,
        h('div', { className: 'td-split' },
          h(Kpi, { label: t('marketValue'), value: money(totals.marketValue), sub: `${totals.count} ${t('positions')}` }),
          h(Kpi, {
            label: t('floatPnl'),
            value: signed(totals.pnl, (value) => money(value)),
            sub: pct(totals.pnlPct),
            tone: toneOf(totals.pnl),
          }),
          h(Kpi, {
            label: t('dayPnl'),
            value: signed(totals.dayPnl, (value) => money(value)),
            sub: totals.priced === 0 ? t('noPrice') : null,
            tone: toneOf(totals.dayPnl),
          }),
          h(Kpi, { label: t('cash'), value: money(totals.cash), sub: currency }),
          h(Kpi, { label: t('equity'), value: money(totals.equity), sub: currency }),
          h(Kpi, {
            label: t('exposure'),
            value: totals.exposure === null ? '—' : `${totals.exposure}%`,
            sub: `${t('priced')} ${totals.priced}/${totals.count}`,
          })),

        snapshot.holdings.length > 0
          ? h('div', { className: 'td-card' },
            h('div', { className: 'td-card-head' },
              h('div', { className: 'td-card-title' }, t('positions')),
              h('button', {
                type: 'button',
                className: 'td-btn td-btn-ghost',
                onClick: onOpenPositions,
              }, t('tabPositions'))),
            h('div', { className: 'td-rows' }, snapshot.holdings.map((holding) => h('div', {
              key: holding.ticker,
              className: 'td-row',
            },
            h('div', null,
              h('div', { className: 'td-symbol' }, holding.ticker),
              h('div', { className: 'td-name' }, holding.name)),
            h('div', { className: 'td-bar' },
              h('span', { style: { width: `${Math.max(2, Math.min(100, holding.weight ?? 0))}%` } })),
            h('div', { style: { display: 'flex', justifyContent: 'flex-end', gap: 8, alignItems: 'center' } },
              h(Sparkline, { values: holding.series, tone: (holding.changePct ?? 0) < 0 ? 'down' : 'up' }),
              h('span', { className: `td-mono ${toneOf(holding.pnl)}` }, signed(holding.pnl, compact)))))))
          : h(Empty, { title: t('emptyHoldings'), hint: t('emptyHoldingsHint') }),

        h('div', { className: 'td-card' },
          h('div', { className: 'td-card-head' },
            h('div', { className: 'td-card-title' }, `${t('todayStrategy')} · ${snapshot.today}`)),
          today
            ? h('div', null,
              today.items.map((item) => h('div', { key: item.ticker, className: 'td-item' },
                h('div', { className: 'td-symbol' }, item.ticker),
                h('div', { className: 'td-item-meta' },
                  h('span', { className: 'td-badge', 'data-tone': ratingTone(item.rating) }, item.rating ?? '—'),
                  item.action ? h('span', { className: 'td-badge' }, item.action) : null,
                  item.entryPrice ? h('span', null, `${t('avgPrice')} ${item.entryPrice}`) : null,
                  item.stopLoss ? h('span', null, `${t('stopLoss')} ${item.stopLoss}`) : null,
                  item.priceTarget ? h('span', null, `${t('target')} ${item.priceTarget}`) : null),
                h('div', { className: 'td-item-summary' }, item.summary ?? ''))),
              today.plan
                ? h('div', { className: 'td-plan' },
                  h('div', { className: 'td-plan-label' }, t('myPlan')),
                  h('div', { className: 'td-plan-body' }, today.plan.body))
                : null)
            : h('div', { className: 'td-muted', style: { fontSize: 12.5 } }, t('noStrategyToday'))),

        snapshot.warnings.length > 0
          ? h('div', { className: 'td-warn' }, snapshot.warnings.join('  '))
          : null);
    }

    const BLANK_FORM = {
      ticker: '', name: '', quantity: '', averagePrice: '', stopLoss: '', targetPrice: '',
      manualPrice: '', note: '',
    };

    function PositionsTab({ snapshot, t, busy, onMutate, onError }) {
      const [editing, setEditing] = React.useState(null);
      const [form, setForm] = React.useState(BLANK_FORM);
      const [cashDraft, setCashDraft] = React.useState(String(snapshot.book.cash ?? 0));
      const [currencyDraft, setCurrencyDraft] = React.useState(snapshot.currency || 'CNY');

      React.useEffect(() => {
        setCashDraft(String(snapshot.book.cash ?? 0));
        setCurrencyDraft(snapshot.currency || 'CNY');
      }, [snapshot.book.cash, snapshot.currency]);

      const startAdd = (seed) => {
        setEditing(seed?.ticker ?? 'new');
        setForm({ ...BLANK_FORM, ...seed });
      };
      const startEdit = (holding) => {
        setEditing(holding.ticker);
        setForm({
          ticker: holding.ticker,
          name: holding.name,
          quantity: String(holding.quantity ?? ''),
          averagePrice: holding.averagePrice === null ? '' : String(holding.averagePrice),
          stopLoss: holding.stopLoss === null ? '' : String(holding.stopLoss),
          targetPrice: holding.targetPrice === null ? '' : String(holding.targetPrice),
          manualPrice: holding.manualPrice === null ? '' : String(holding.manualPrice),
          note: holding.note ?? '',
        });
      };
      const numeric = (value) => (value === '' || value === null || value === undefined ? null : Number(value));

      const submit = async (event) => {
        event.preventDefault();
        if (!form.ticker.trim()) {
          onError(new Error(t('symbolRequired')));
          return;
        }
        const ok = await onMutate('upsertPosition', {
          ticker: form.ticker.trim().toUpperCase(),
          name: form.name.trim() || undefined,
          quantity: numeric(form.quantity) ?? 0,
          averagePrice: numeric(form.averagePrice),
          stopLoss: numeric(form.stopLoss),
          targetPrice: numeric(form.targetPrice),
          manualPrice: numeric(form.manualPrice),
          note: form.note,
        });
        if (ok) {
          setEditing(null);
          setForm(BLANK_FORM);
        }
      };

      const analysed = [];
      const seen = new Set();
      for (const record of snapshot.records) {
        if (!seen.has(record.ticker)) {
          seen.add(record.ticker);
          analysed.push(record);
        }
      }
      const held = new Set(snapshot.holdings.map((holding) => holding.ticker));
      const quick = analysed.filter((record) => !held.has(record.ticker)).slice(0, 8);

      return h(React.Fragment, null,
        h('div', { className: 'td-toolbar' },
          h('div', { className: 'td-toolbar-left' },
            `${snapshot.totals.count} ${t('positions')}`,
            h('span', null, '·'),
            `${t('marketValue')} ${money(snapshot.totals.marketValue, snapshot.currency)}`),
          h('div', { style: { display: 'flex', gap: 8 } },
            h('button', {
              type: 'button',
              className: 'td-btn td-btn-primary',
              onClick: () => startAdd(null),
              disabled: busy,
            }, `＋ ${t('addPosition')}`))),

        editing !== null
          ? h('form', { className: 'td-card', onSubmit: submit },
            h('div', { className: 'td-card-title' }, editing === 'new' ? t('addPosition') : `${t('edit')} ${editing}`),
            h('div', { className: 'td-form' },
              h('label', { className: 'td-field' },
                h('span', null, t('ticker')),
                h('input', {
                  className: 'td-input',
                  value: form.ticker,
                  placeholder: '600036.SS',
                  onChange: (event) => setForm({ ...form, ticker: event.target.value }),
                  disabled: editing !== 'new',
                })),
              h('label', { className: 'td-field' },
                h('span', null, t('name')),
                h('input', {
                  className: 'td-input',
                  value: form.name,
                  placeholder: '招商银行',
                  onChange: (event) => setForm({ ...form, name: event.target.value }),
                })),
              h('label', { className: 'td-field' },
                h('span', null, t('quantity')),
                h('input', {
                  className: 'td-input',
                  value: form.quantity,
                  inputMode: 'decimal',
                  onChange: (event) => setForm({ ...form, quantity: event.target.value }),
                })),
              h('label', { className: 'td-field' },
                h('span', null, t('avgPrice')),
                h('input', {
                  className: 'td-input',
                  value: form.averagePrice,
                  inputMode: 'decimal',
                  onChange: (event) => setForm({ ...form, averagePrice: event.target.value }),
                })),
              h('label', { className: 'td-field' },
                h('span', null, t('stopLoss')),
                h('input', {
                  className: 'td-input',
                  value: form.stopLoss,
                  inputMode: 'decimal',
                  onChange: (event) => setForm({ ...form, stopLoss: event.target.value }),
                })),
              h('label', { className: 'td-field' },
                h('span', null, t('target')),
                h('input', {
                  className: 'td-input',
                  value: form.targetPrice,
                  inputMode: 'decimal',
                  onChange: (event) => setForm({ ...form, targetPrice: event.target.value }),
                })),
              h('label', { className: 'td-field' },
                h('span', null, t('manualPrice')),
                h('input', {
                  className: 'td-input',
                  value: form.manualPrice,
                  inputMode: 'decimal',
                  placeholder: '1.712',
                  onChange: (event) => setForm({ ...form, manualPrice: event.target.value }),
                })),
              h('div', { className: 'td-muted', style: { fontSize: 11, gridColumn: '1 / -1' } }, t('priceHint')),
              h('label', { className: 'td-field', style: { gridColumn: '1 / -1' } },
                h('span', null, t('note')),
                h('input', {
                  className: 'td-input',
                  value: form.note,
                  onChange: (event) => setForm({ ...form, note: event.target.value }),
                })),
              h('div', { className: 'td-form-actions' },
                h('button', {
                  type: 'button',
                  className: 'td-btn',
                  onClick: () => { setEditing(null); setForm(BLANK_FORM); },
                }, t('cancel')),
                h('button', { type: 'submit', className: 'td-btn td-btn-primary', disabled: busy },
                  busy ? t('saving') : t('save')))))
          : null,

        snapshot.holdings.length === 0
          ? h('div', { style: { marginTop: 14 } }, h(Empty, { title: t('emptyHoldings'), hint: t('emptyHoldingsHint') }))
          : h('div', { className: 'td-table-wrap' },
            h('table', { className: 'td-table' },
              h('thead', null, h('tr', null,
                h('th', null, t('ticker')),
                h('th', null, t('name')),
                h('th', null, t('quantity')),
                h('th', null, `${t('cost')}`),
                h('th', null, t('lastPrice')),
                h('th', null, t('marketValue')),
                h('th', null, t('pnl')),
                h('th', null, t('stopLoss')),
                h('th', null, t('weightOf')),
                h('th', null, t('actions')))),
              h('tbody', null, snapshot.holdings.map((holding) => h('tr', { key: holding.ticker },
                h('td', null, h('div', { className: 'td-symbol' }, holding.ticker)),
                h('td', null, h('div', { className: 'td-name' }, holding.name)),
                h('td', null, holding.quantity),
                h('td', null, money(holding.averagePrice)),
                h('td', null, holding.last === null
                  ? h('span', { className: 'td-name' }, t('noPrice'))
                  : h('span', null,
                    money(holding.last),
                    holding.priceSource === 'manual'
                      ? h('span', { className: 'td-name', style: { marginLeft: 4 } }, t('manualTag'))
                      : null)),
                h('td', null, money(holding.marketValue)),
                h('td', { className: toneOf(holding.pnl) },
                  signed(holding.pnl, (value) => money(value)),
                  h('div', { className: 'td-name' }, pct(holding.pnlPct))),
                h('td', null, holding.stopLoss === null ? '—' : money(holding.stopLoss)),
                h('td', null, holding.weight === null ? '—' : `${holding.weight}%`),
                h('td', null, h('div', { style: { display: 'flex', gap: 6, justifyContent: 'flex-end' } },
                  h('button', {
                    type: 'button',
                    className: 'td-btn td-btn-ghost',
                    onClick: () => startEdit(holding),
                    disabled: busy,
                  }, t('edit')),
                  h('button', {
                    type: 'button',
                    className: 'td-btn td-btn-ghost td-btn-danger',
                    onClick: () => onMutate('removePosition', { ticker: holding.ticker }),
                    disabled: busy,
                  }, t('remove'))))))))),

        quick.length > 0
          ? h('div', { className: 'td-card' },
            h('div', { className: 'td-card-title' }, t('quickAdd')),
            h('div', { className: 'td-chips' }, quick.map((record) => h('button', {
              key: record.ticker,
              type: 'button',
              className: 'td-chip',
              onClick: () => startAdd({ ticker: record.ticker, name: record.ticker }),
            }, record.ticker))))
          : null,

        h('div', { className: 'td-card' },
          h('div', { className: 'td-card-title', style: { marginBottom: 10 } }, t('cashEditor')),
          h('div', { className: 'td-inline-form' },
            h('label', { className: 'td-field' },
              h('span', null, t('cash')),
              h('input', {
                className: 'td-input',
                value: cashDraft,
                inputMode: 'decimal',
                onChange: (event) => setCashDraft(event.target.value),
              })),
            h('label', { className: 'td-field' },
              h('span', null, t('currency')),
              h('select', {
                className: 'td-select',
                value: currencyDraft,
                onChange: (event) => setCurrencyDraft(event.target.value),
              }, ['CNY', 'HKD', 'USD'].map((code) => h('option', { key: code, value: code }, code)))),
            h('button', {
              type: 'button',
              className: 'td-btn',
              disabled: busy,
              onClick: () => onMutate('setCash', {
                cash: Number(cashDraft),
                currency: currencyDraft,
              }),
            }, busy ? t('saving') : t('save')))));
    }

    function StrategiesTab({ snapshot, t, busy, onMutate }) {
      const [editingDate, setEditingDate] = React.useState(null);
      const [draft, setDraft] = React.useState('');

      const days = React.useMemo(() => {
        const list = snapshot.strategies.slice();
        if (!list.some((day) => day.date === snapshot.today)) {
          list.unshift({ date: snapshot.today, items: [], plan: null });
        }
        return list;
      }, [snapshot.strategies, snapshot.today]);

      if (days.length === 0) return h(Empty, { title: t('noStrategies') });

      const begin = (day) => {
        setEditingDate(day.date);
        setDraft(day.plan?.body ?? '');
      };
      const save = async (date) => {
        const ok = await onMutate('saveJournal', { date, kind: 'strategy', body: draft });
        if (ok) setEditingDate(null);
      };

      return h('div', null, days.map((day) => h('div', { key: day.date, className: 'td-day' },
        h('div', { className: 'td-day-head' },
          h('div', { className: 'td-day-date' },
            day.date,
            day.date === snapshot.today ? h('span', { className: 'td-badge', style: { marginLeft: 8 } }, 'today') : null),
          h('div', { style: { display: 'flex', gap: 8 } },
            editingDate === day.date ? null : h('button', {
              type: 'button',
              className: 'td-btn td-btn-ghost',
              onClick: () => begin(day),
              disabled: busy,
            }, day.plan ? t('editPlan') : t('writePlan')))),
        day.items.length === 0
          ? h('div', { className: 'td-muted', style: { fontSize: 12.5, marginTop: 8 } }, t('noStrategyToday'))
          : day.items.map((item) => h('div', { key: item.ticker, className: 'td-item' },
            h('div', { className: 'td-symbol' }, item.ticker),
            h('div', { className: 'td-item-meta' },
              h('span', { className: 'td-badge', 'data-tone': ratingTone(item.rating) }, item.rating ?? '—'),
              item.action ? h('span', { className: 'td-badge' }, item.action) : null,
              item.entryPrice ? h('span', null, `${t('avgPrice')} ${item.entryPrice}`) : null,
              item.stopLoss ? h('span', null, `${t('stopLoss')} ${item.stopLoss}`) : null,
              item.priceTarget ? h('span', null, `${t('target')} ${item.priceTarget}`) : null,
              item.horizon ? h('span', null, item.horizon) : null),
            h('div', { className: 'td-item-summary' }, item.summary ?? ''))),
        h('div', { className: 'td-plan' },
          h('div', { className: 'td-plan-label' }, t('myPlan')),
          editingDate === day.date
            ? h('div', null,
              h('textarea', {
                className: 'td-textarea',
                value: draft,
                placeholder: t('planPlaceholder'),
                onChange: (event) => setDraft(event.target.value),
              }),
              h('div', { className: 'td-form-actions', style: { marginTop: 8 } },
                h('button', {
                  type: 'button',
                  className: 'td-btn',
                  onClick: () => setEditingDate(null),
                }, t('cancel')),
                h('button', {
                  type: 'button',
                  className: 'td-btn td-btn-primary',
                  disabled: busy,
                  onClick: () => save(day.date),
                }, busy ? t('saving') : t('save'))))
            : h('div', { className: day.plan ? 'td-plan-body' : 'td-muted', style: { fontSize: 12.5 } },
              day.plan ? day.plan.body : t('planPlaceholder'))))));
    }

    function WatchlistTab({ snapshot, t }) {
      const watchlist = snapshot.watchlist ?? { items: [] };
      const items = Array.isArray(watchlist.items) ? watchlist.items : [];
      if (items.length === 0) return h(Empty, { title: t('noWatchlist'), hint: t('noWatchlistHint') });

      const tone = (status) => {
        if (status === '已买入') return 'buy';
        if (status === '已放弃' || status === '放弃') return 'sell';
        return 'hold';
      };
      const num = (value) => (value === null || value === undefined ? '—' : String(value));
      const band = (item) => {
        if (item.buyLow === null || item.buyLow === undefined) return '—';
        if (item.buyHigh === null || item.buyHigh === undefined || item.buyHigh === item.buyLow) {
          return String(item.buyLow);
        }
        return `${item.buyLow}–${item.buyHigh}`;
      };
      const columns = [
        '#', t('ticker'), t('name'), t('buyBand'), t('stopLoss'), t('target'), t('sizeLabel'), t('status'),
        t('conditionReason'),
      ];

      return h('div', { className: 'td-day' },
        h('div', { className: 'td-day-head' },
          h('div', { className: 'td-day-date' }, `${t('watchlist')} · ${watchlist.date || '—'}`),
          h('div', { className: 'td-muted', style: { fontSize: 12 } },
            watchlist.updatedAt
              ? `${t('generatedAt')} ${new Date(watchlist.updatedAt).toLocaleString(undefined, { hour12: false })}`
              : '')),
        watchlist.note
          ? h('div', { className: 'td-plan-body', style: { fontSize: 12.5, marginBottom: 10 } }, watchlist.note)
          : null,
        h('div', { className: 'td-table-wrap' },
          h('table', { className: 'td-table' },
            h('thead', null, h('tr', null, columns.map((label, index) => h('th', {
              key: label,
              style: index === columns.length - 1 ? { textAlign: 'left', minWidth: 320 } : null,
            }, label)))),
            h('tbody', null, items.map((item, index) => h('tr', { key: item.ticker },
              h('td', null, index + 1),
              h('td', { className: 'td-symbol' }, item.ticker),
              h('td', null, item.name),
              h('td', { className: 'td-mono' }, band(item)),
              h('td', { className: 'td-mono' }, num(item.stopLoss)),
              h('td', { className: 'td-mono' }, num(item.target)),
              h('td', null, item.size || '—'),
              h('td', null, h('span', { className: 'td-badge', 'data-tone': tone(item.status) },
                item.status || '待触发')),
              h('td', { style: { textAlign: 'left', whiteSpace: 'normal', minWidth: 320 } },
                item.condition ? h('div', null, item.condition) : null,
                item.reason
                  ? h('div', { className: 'td-muted', style: { fontSize: 12, marginTop: 2 } }, item.reason)
                  : null)))))));
    }

    function RecordsTab({ snapshot, t, busy, onMutate }) {
      const [title, setTitle] = React.useState('');
      const [body, setBody] = React.useState('');

      const save = async () => {
        if (!body.trim()) return;
        const ok = await onMutate('saveJournal', {
          date: snapshot.today,
          kind: 'note',
          title: title.trim(),
          body,
        });
        if (ok) {
          setTitle('');
          setBody('');
        }
      };

      return h('div', null,
        h('div', { className: 'td-card' },
          h('div', { className: 'td-card-head' },
            h('div', { className: 'td-card-title' }, t('journal')),
            h('span', { className: 'td-pill' }, `${snapshot.journal.length}`)),
          h('div', { className: 'td-form' },
            h('label', { className: 'td-field', style: { gridColumn: '1 / -1' } },
              h('span', null, t('noteTitle')),
              h('input', {
                className: 'td-input',
                value: title,
                placeholder: `${snapshot.today} 交易复盘`,
                onChange: (event) => setTitle(event.target.value),
              })),
            h('label', { className: 'td-field', style: { gridColumn: '1 / -1' } },
              h('span', null, t('noteBody')),
              h('textarea', {
                className: 'td-textarea',
                value: body,
                placeholder: t('planPlaceholder'),
                onChange: (event) => setBody(event.target.value),
              })),
            h('div', { className: 'td-form-actions' },
              h('button', {
                type: 'button',
                className: 'td-btn td-btn-primary',
                disabled: busy || !body.trim(),
                onClick: save,
              }, busy ? t('saving') : t('addNote'))))),
        snapshot.journal.length > 0
          ? h('div', { className: 'td-card' }, snapshot.journal.map((entry) => h('div', {
            key: entry.id,
            className: 'td-journal',
          },
          h('div', { className: 'td-journal-head' },
            h('div', null,
              h('span', { className: 'td-mono td-muted' }, entry.date),
              ' ',
              h('span', { className: 'td-badge' }, entry.kind === 'strategy' ? t('journalKindStrategy') : t('journalKindNote')),
              entry.ticker ? h('span', { className: 'td-mono', style: { marginLeft: 8 } }, entry.ticker) : null,
              entry.title ? h('span', { style: { marginLeft: 8, fontWeight: 600 } }, entry.title) : null),
            h('button', {
              type: 'button',
              className: 'td-btn td-btn-ghost td-btn-danger',
              disabled: busy,
              onClick: () => onMutate('deleteJournal', { id: entry.id }),
            }, t('delete'))),
          h('div', { className: 'td-journal-body' }, entry.body))))
          : h('div', { className: 'td-card' }, h(Empty, { title: t('noJournal') })),

        h('div', { className: 'td-card' },
          h('div', { className: 'td-card-head' },
            h('div', { className: 'td-card-title' }, t('records')),
            h('span', { className: 'td-pill' }, `${snapshot.records.length} ${t('runs')}`)),
          snapshot.records.length === 0
            ? h('div', { className: 'td-muted', style: { fontSize: 12.5 } }, t('noRecords'))
            : snapshot.records.map((record) => h('div', { key: record.id, className: 'td-record' },
              h('div', { className: 'td-record-head' },
                h('span', { className: 'td-mono td-muted' }, record.date),
                h('span', { className: 'td-symbol' }, record.ticker),
                h('span', { className: 'td-badge', 'data-tone': ratingTone(record.rating) }, record.rating ?? '—'),
                record.action ? h('span', { className: 'td-badge' }, record.action) : null,
                record.priceTarget ? h('span', { className: 'td-muted' }, `${t('target')} ${record.priceTarget}`) : null,
                record.stopLoss ? h('span', { className: 'td-muted' }, `${t('stopLoss')} ${record.stopLoss}`) : null,
                record.horizon ? h('span', { className: 'td-muted' }, record.horizon) : null),
              record.summary ? h('div', { className: 'td-record-summary' }, record.summary) : null,
              h('div', { className: 'td-record-metrics' },
                record.metrics
                  ? [
                    record.metrics.totalTokens ? `${record.metrics.totalTokens} ${t('tokens')}` : null,
                    record.metrics.elapsedSeconds ? `${Math.round(record.metrics.elapsedSeconds)}s` : null,
                    record.metrics.analysts?.length ? record.metrics.analysts.join('/') : null,
                  ].filter(Boolean).join(' · ')
                  : '—',
                ' · ',
                h('span', { className: 'td-muted' }, record.path))))));
    }

    /* -------------------------------------------------------------- page */

    function makePage(ctx, fallbackRpc) {
      function TradingDeskPage(props) {
        const t = useTranslator(ctx);
        // The slot's `inject` provider supplies this; the closure copy keeps the
        // page working if a shell projects only the owner props.
        const rpc = props?.rpc ?? fallbackRpc;
        const [tab, setTab] = React.useState('overview');
        const [snapshot, setSnapshot] = React.useState(null);
        const [error, setError] = React.useState(null);
        const [busy, setBusy] = React.useState(false);
        const [loading, setLoading] = React.useState(true);

        const load = React.useCallback(async () => {
          if (typeof rpc !== 'function') return;
          setLoading(true);
          setError(null);
          try {
            const value = await rpc('snapshot', {});
            setSnapshot(value);
            publishDesk(value);
          } catch (cause) {
            setError(cause?.message ?? String(cause));
          } finally {
            setLoading(false);
          }
        }, [rpc]);

        React.useEffect(() => {
          load();
        }, [load]);

        const mutate = React.useCallback(async (method, payload) => {
          if (typeof rpc !== 'function') return false;
          setBusy(true);
          setError(null);
          try {
            const value = await rpc(method, payload);
            setSnapshot(value);
            publishDesk(value);
            return true;
          } catch (cause) {
            setError(cause?.message ?? String(cause));
            return false;
          } finally {
            setBusy(false);
          }
        }, [rpc]);

        const reportError = React.useCallback((cause) => {
          setError(cause?.message ?? String(cause));
        }, []);

        if (loading && !snapshot) {
          return h('div', { className: 'td-page' }, h(Styles), h('div', { className: 'td-loading' }, t('loading')));
        }

        if (!snapshot) {
          return h('div', { className: 'td-page' }, h(Styles),
            h('div', { className: 'td-body' },
              h('div', { className: 'td-error' }, error ?? t('failed')),
              h('button', { type: 'button', className: 'td-btn', onClick: load }, t('retry'))));
        }

        const tabs = [
          { id: 'overview', label: t('tabOverview') },
          { id: 'positions', label: t('tabPositions') },
          { id: 'strategies', label: t('tabStrategies') },
          { id: 'watchlist', label: t('tabWatchlist') },
          { id: 'records', label: t('tabRecords') },
        ];

        let content = null;
        if (tab === 'positions') {
          content = h(PositionsTab, { snapshot, t, busy, onMutate: mutate, onError: reportError });
        } else if (tab === 'strategies') {
          content = h(StrategiesTab, { snapshot, t, busy, onMutate: mutate });
        } else if (tab === 'watchlist') {
          content = h(WatchlistTab, { snapshot, t });
        } else if (tab === 'records') {
          content = h(RecordsTab, { snapshot, t, busy, onMutate: mutate });
        } else {
          content = h(OverviewTab, { snapshot, t, onOpenPositions: () => setTab('positions') });
        }

        const updated = snapshot.generatedAt
          ? new Date(snapshot.generatedAt).toLocaleString(undefined, { hour12: false })
          : '—';

        const header = h('header', { className: 'td-head' },
          h('div', { style: { minWidth: 0 } },
            h('div', { className: 'td-title' }, t('title')),
            h('div', { className: 'td-sub' },
              `${t('workspace')} ${snapshot.root}`,
              snapshot.detected ? '' : ` · ${t('notDetected')}`),
            h('div', { className: 'td-sub' },
              `${t('generatedAt')} ${updated}`,
              ` · ${snapshot.coverage.reports} ${t('runs')}`,
              ` · ${snapshot.coverage.tickers} symbols`)),
          h('div', { className: 'td-head-actions' },
            h('span', { className: 'td-pill' },
              snapshot.detected ? t('detected') : t('notDetected')),
            h('button', {
              type: 'button',
              className: 'td-btn',
              onClick: load,
              disabled: loading,
            }, loading ? t('loading') : t('refresh'))));

        const nav = h('nav', { className: 'td-tabs' }, tabs.map((entry) => h('button', {
          key: entry.id,
          type: 'button',
          className: 'td-tab',
          'data-active': tab === entry.id ? 'true' : 'false',
          onClick: () => setTab(entry.id),
        }, entry.label)));

        const body = h('div', { className: 'td-body' },
          error ? h('div', { className: 'td-error' }, error) : null,
          content);

        return h('div', { className: 'td-page' }, h(Styles), header, nav, body);
      }
      return TradingDeskPage;
    }

    // Compact seat at the sidebar foot: live book summary that opens the panel.
    function makeFooter(ctx, fallbackRpc, open) {
      function DeskFooter(props) {
        const t = useTranslator(ctx);
        const rpc = props?.rpc ?? fallbackRpc;
        const [snapshot, setSnapshot] = React.useState(deskSnapshot);
        // Undeclared width degrades to the rail glyph rather than a row that
        // could overflow a 56px column.
        const wide = props?.wide === true;

        React.useEffect(() => subscribeDesk(setSnapshot), []);

        // Only the first row to mount asks the Host; later ones read the cache.
        React.useEffect(() => {
          if (deskSnapshot || typeof rpc !== 'function') return undefined;
          let alive = true;
          rpc('snapshot', {}).then((value) => {
            if (!alive) return;
            setSnapshot(value);
            publishDesk(value);
          }).catch(() => {});
          return () => {
            alive = false;
          };
        }, [rpc]);

        // Prices and the book also change outside this client, so a slow poll
        // keeps the row honest without touching the Host while the page is hidden.
        React.useEffect(() => {
          if (typeof rpc !== 'function') return undefined;
          const refresh = () => {
            if (document.visibilityState === 'hidden') return;
            rpc('snapshot', {}).then(publishDesk).catch(() => {});
          };
          const timer = window.setInterval(refresh, 90000);
          document.addEventListener('visibilitychange', refresh);
          return () => {
            window.clearInterval(timer);
            document.removeEventListener('visibilitychange', refresh);
          };
        }, [rpc]);

        const totals = snapshot?.totals;
        const tone = totals ? toneOf(totals.pnl) : '';
        const tip = deskTooltip(snapshot, t);
        return h('button', {
          type: 'button',
          className: 'td-foot',
          'data-wide': wide ? 'true' : 'false',
          onClick: open,
          title: tip,
          'aria-label': tip,
        },
        h(SidebarIcon, { size: 16 }),
        wide ? h('span', { className: 'td-foot-label' }, t('title')) : null,
        wide && totals && totals.count > 0
          ? h('span', { className: `td-foot-value ${tone}` }, pct(totals.pnlPct))
          : null);
      }
      return DeskFooter;
    }

    function SidebarIcon({ size }) {
      const edge = Number.isFinite(size) ? size : 16;
      return h('svg', {
        width: edge,
        height: edge,
        viewBox: '0 0 16 16',
        fill: 'none',
        stroke: 'currentColor',
        strokeWidth: 1.1,
        strokeLinecap: 'round',
        strokeLinejoin: 'round',
        'aria-hidden': true,
        focusable: false,
      },
        h('path', { d: 'M2 13.5h12' }),
        h('path', { d: 'M4 13.5V9' }),
        h('path', { d: 'M7.2 13.5V6' }),
        h('path', { d: 'M10.4 13.5V8' }),
        h('path', { d: 'M13.6 13.5V3.5' }),
        h('path', { d: 'M2.6 8.4 6 6l2.8 1.6L13.4 3' }));
    }

    return {
      inject: ['slots', 'connection', 'locale'],
      apply(ctx) {
        let caller = null;
        try {
          caller = ctx.connection?.rpc?.call ? ctx.connection : null;
        } catch {
          caller = null;
        }

        const rpc = async (method, payload) => {
          if (!caller) throw new Error('DSH connection is not available');
          const result = await caller.rpc.call('/api', RPC_CHANNEL, { method, payload }, undefined);
          if (!result || result.ok !== true) {
            throw new Error(result?.error?.message ?? 'trading desk request failed');
          }
          return result.value;
        };

        const Page = makePage(ctx, rpc);
        const label = () => {
          const tag = ctx.locale?.getLocale?.()?.active ?? '';
          return makeT(tag)('title');
        };

        ctx.slots.inject('main', () => {
          const stopPage = ctx.slots.register({
            name: 'main',
            key: PANEL_ID,
            inject: () => ({ rpc }),
          }, Page);
          const stopSidebar = ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
            name: 'sidebar.panellist',
            id: PANEL_ID,
            order: 6,
            label,
          }, SidebarIcon));
          return () => {
            stopSidebar();
            stopPage();
          };
        });

        ctx.inject(['layout'], (layoutCtx) => {
          const Footer = makeFooter(ctx, rpc, () => layoutCtx.layout.selectPanel(PANEL_ID));
          layoutCtx.effect(() => layoutCtx.slots.inject('sidebar.footer.action', () => layoutCtx.slots.register({
            name: 'sidebar.footer.action',
            id: 'trading-desk-foot',
            order: 6,
            label,
            inject: () => ({ rpc }),
          }, Footer)), 'trading desk: sidebar summary');
        });
      },
    };
  },
});
