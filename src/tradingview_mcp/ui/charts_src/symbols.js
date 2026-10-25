const HYPERLIQUID_GROUP = {
  label: 'Crypto · Hyperliquid',
  symbols: [
    { id: 'BTC', label: 'BTC-PERP', source: 'hyperliquid' },
    { id: 'ETH', label: 'ETH-PERP', source: 'hyperliquid' },
    { id: 'SOL', label: 'SOL-PERP', source: 'hyperliquid' },
    { id: 'HYPE', label: 'HYPE-PERP', source: 'hyperliquid' },
  ],
};

const FALLBACK_YAHOO_SYMBOLS = [
  'AAPL','SPY','QQQ','BTC-USD','NVDA','DIA','GDX','VXX','AGNC','AMD','AMZN','BE',
  'BMNR','BMRN','CRWD','ETH-USD','GOOGL','IREN','MELI','META','MSFT','NVTS','PAAS',
  'PANW','PLTR','SMCI','SMR','SNDK','SOL-USD','STX','TSLA','UEC','WDC','WULF',
];

const ADDITIONAL_YAHOO_SYMBOLS = [
  { id: 'RELIANCE.NS', label: 'RELIANCE', source: 'yahoo' },
  { id: 'TCS.NS', label: 'TCS', source: 'yahoo' },
  { id: 'INFY.NS', label: 'INFY', source: 'yahoo' },
  { id: 'HDFCBANK.NS', label: 'HDFCBANK', source: 'yahoo' },
  { id: '^NSEI', label: 'NIFTY 50', source: 'yahoo' },
];

const yahooSymbol = (id) => ({ id, label: id, source: 'yahoo' });

export function buildSymbolGroups(dashboardSymbols = FALLBACK_YAHOO_SYMBOLS) {
  const dashboard = [...new Set(dashboardSymbols.filter(Boolean).map((id) => String(id).trim().toUpperCase()))];
  const dashboardIds = new Set(dashboard);
  const additional = ADDITIONAL_YAHOO_SYMBOLS.filter((symbol) => !dashboardIds.has(symbol.id));
  return [
    HYPERLIQUID_GROUP,
    { label: 'Strategy Dashboard · Yahoo', symbols: dashboard.map(yahooSymbol) },
    ...(additional.length ? [{ label: 'Additional Yahoo Markets', symbols: additional }] : []),
  ];
}

export function filterSymbolGroups(groups, query) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return groups;
  return groups
    .map((group) => ({
      ...group,
      symbols: group.symbols.filter((symbol) =>
        symbol.id.toLowerCase().includes(normalized)
        || symbol.label.toLowerCase().includes(normalized)
        || group.label.toLowerCase().includes(normalized)),
    }))
    .filter((group) => group.symbols.length);
}

export const SYMBOL_GROUPS = buildSymbolGroups();

export function findSymbol(id, groups = SYMBOL_GROUPS) {
  return groups.flatMap((group) => group.symbols).find((symbol) => symbol.id === id)
    ?? SYMBOL_GROUPS[0].symbols[0];
}

export const DEFAULT_PANE_SYMBOLS = ['BTC','AAPL','ETH','SPY','SOL','NVDA','HYPE','GOOGL'];
