// One shared WebSocket for every pane; subscriptions are ref-counted per coin/interval.

const WS_URL = 'wss://api.hyperliquid.xyz/ws';
const PING_INTERVAL_MS = 30000;
const RECONNECT_DELAY_MS = 2000;
// Grace period before closing an idle socket, so StrictMode's
// mount/unmount/mount cycle doesn't tear down a connecting socket.
const IDLE_CLOSE_MS = 1000;

const listeners = new Map();
let socket = null;
let pingTimer = null;
let reconnectTimer = null;
let idleTimer = null;

const keyOf = (coin, interval) => `${coin}:${interval}`;

function send(method, key) {
  if (socket?.readyState !== WebSocket.OPEN) return;
  const [coin, interval] = key.split(':');
  socket.send(JSON.stringify({ method, subscription: { type: 'candle', coin, interval } }));
}

function handleMessage(event) {
  const message = JSON.parse(event.data);
  if (message.channel !== 'candle') return;
  const { s: coin, i: interval } = message.data;
  listeners.get(keyOf(coin, interval))?.forEach((listener) => listener(message.data));
}

function handleOpen() {
  listeners.forEach((_, key) => send('subscribe', key));
  pingTimer = setInterval(() => socket?.send(JSON.stringify({ method: 'ping' })), PING_INTERVAL_MS);
}

function handleClose() {
  clearInterval(pingTimer);
  socket = null;
  if (listeners.size === 0) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, RECONNECT_DELAY_MS);
}

function connect() {
  socket = new WebSocket(WS_URL);
  socket.onopen = handleOpen;
  socket.onmessage = handleMessage;
  socket.onclose = handleClose;
}

function disconnect() {
  clearTimeout(reconnectTimer);
  clearInterval(pingTimer);
  reconnectTimer = null;
  if (!socket) return;
  socket.onclose = null;
  socket.close();
  socket = null;
}

export function subscribeHyperliquidCandles(coin, interval, listener) {
  const key = keyOf(coin, interval);
  clearTimeout(idleTimer);
  if (!listeners.has(key)) {
    listeners.set(key, new Set());
    send('subscribe', key);
  }
  listeners.get(key).add(listener);
  if (!socket && !reconnectTimer) connect();

  return () => {
    const keyListeners = listeners.get(key);
    keyListeners?.delete(listener);
    if (keyListeners?.size === 0) {
      listeners.delete(key);
      send('unsubscribe', key);
    }
    if (listeners.size === 0) idleTimer = setTimeout(disconnect, IDLE_CLOSE_MS);
  };
}
