/**
 * Local sanity check for the data layer. Runs against the real workspace so a
 * parsing or P&L regression shows up before the panel is opened.
 *
 *   node .dsh-plugins/trading-desk/scripts/selftest.mjs
 */
import path from 'node:path';
import {
  buildSnapshot,
  isTradingAgentsRoot,
  readPrices,
  resolveRoot,
  tickerCandidates,
} from '../lib/data.js';

const root = path.resolve(process.argv[2] ?? process.cwd());
const fakeCtx = { get: () => undefined };
const resolved = resolveRoot(fakeCtx, {});
const snapshot = buildSnapshot(root, { currency: 'CNY' });

console.log('root           ', root);
console.log('detected       ', isTradingAgentsRoot(root));
console.log('resolved root  ', resolved);
console.log('ticker cands   ', tickerCandidates('600036.SH').join(' | '));
console.log('prices 600519  ', JSON.stringify(readPrices(root, '600519.SS'))?.slice(0, 160));
console.log('coverage       ', JSON.stringify(snapshot.coverage));
console.log('totals         ', JSON.stringify(snapshot.totals));
console.log('holdings       ', snapshot.holdings.map((h) => `${h.ticker} qty=${h.quantity} last=${h.last} pnl=${h.pnl}`));
console.log('records        ', snapshot.records.length);
for (const record of snapshot.records.slice(0, 4)) {
  console.log('  ', record.date, record.ticker, record.rating, record.action, record.priceTarget, record.stopLoss,
    `metrics=${record.metrics ? record.metrics.totalTokens : 'none'}`);
}
console.log('strategies     ', snapshot.strategies.map((s) => `${s.date}[${s.items.length}]`).join(' '));
console.log('memory         ', snapshot.memory.length, JSON.stringify(snapshot.memory[0]));
console.log('journal        ', snapshot.journal.length);
console.log('warnings       ', snapshot.warnings);
