export const SYMBOL_GROUPS = [
  {
    label: 'Crypto · Hyperliquid',
    symbols: [
      { id: 'BTC', label: 'BTC-PERP', source: 'hyperliquid' },
      { id: 'ETH', label: 'ETH-PERP', source: 'hyperliquid' },
      { id: 'SOL', label: 'SOL-PERP', source: 'hyperliquid' },
      { id: 'HYPE', label: 'HYPE-PERP', source: 'hyperliquid' },
    ],
  },
  {
    label: 'US Stocks · Yahoo',
    symbols: ['AAPL','SPY','QQQ','NVDA','AMD','AMZN','GOOGL','META','MSFT','TSLA','PLTR','MELI'].map((id) => ({ id, label: id, source: 'yahoo' })),
  },
  {
    label: 'Indian Stocks · Yahoo',
    symbols: [
      { id: 'RELIANCE.NS', label: 'RELIANCE', source: 'yahoo' },
      { id: 'TCS.NS', label: 'TCS', source: 'yahoo' },
      { id: 'INFY.NS', label: 'INFY', source: 'yahoo' },
      { id: 'HDFCBANK.NS', label: 'HDFCBANK', source: 'yahoo' },
      { id: '^NSEI', label: 'NIFTY 50', source: 'yahoo' },
    ],
  },
];

const SYMBOLS = new Map(SYMBOL_GROUPS.flatMap((group) => group.symbols).map((symbol) => [symbol.id, symbol]));
export const findSymbol = (id) => SYMBOLS.get(id) ?? SYMBOL_GROUPS[0].symbols[0];
export const DEFAULT_PANE_SYMBOLS = ['BTC','AAPL','ETH','SPY','SOL','NVDA','HYPE','GOOGL'];
