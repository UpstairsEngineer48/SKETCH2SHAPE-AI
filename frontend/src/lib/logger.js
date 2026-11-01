// Browser-side logger.
//  - prints to the devtools console as "[FE] ..."
//  - keeps the last 500 events in memory (window.__s2sLogs, or dumpLogs())
//  - ships events to the backend (POST /api/client-log) where they land in
//    backend/logs/frontend.log, separate from backend.log
//
// Env (frontend/.env):
//   VITE_LOG_LEVEL    debug | info | warn | error   (default: debug in dev, info in build)
//   VITE_REMOTE_LOGS  set to 0 to keep logs in the browser only
//   VITE_LOG_PATH     default /client-log

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
const ENDPOINT = `${API_BASE}${import.meta.env.VITE_LOG_PATH || '/client-log'}`;
const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };
const MIN_LEVEL = LEVELS[import.meta.env.VITE_LOG_LEVEL] || (import.meta.env.DEV ? LEVELS.debug : LEVELS.info);
const REMOTE = import.meta.env.VITE_REMOTE_LOGS !== '0';
const FLUSH_MS = 3000;
const MAX_BUFFER = 500;
const MAX_QUEUE = 200;

const session = Math.random().toString(36).slice(2, 10);
const history = [];
let queue = [];
let timer = null;

function send(events, { beacon = false } = {}) {
  if (!REMOTE || !events.length) return;
  const body = JSON.stringify({ session, events });
  try {
    if (beacon && navigator.sendBeacon) {
      navigator.sendBeacon(ENDPOINT, new Blob([body], { type: 'application/json' }));
      return;
    }
    // never log failures here: that would loop
    fetch(ENDPOINT, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }).catch(() => {});
  } catch { /* logging must never break the app */ }
}

export function flush(opts) {
  clearTimeout(timer);
  timer = null;
  const batch = queue;
  queue = [];
  send(batch, opts);
}

function emit(level, msg, data) {
  if (LEVELS[level] < MIN_LEVEL) return;
  const event = { t: new Date().toISOString(), level: level === 'warn' ? 'warning' : level, msg, ...(data !== undefined ? { data } : {}) };
  history.push(event);
  if (history.length > MAX_BUFFER) history.shift();

  const fn = level === 'debug' ? 'debug' : level;
  console[fn](`[FE ${level}]`, msg, ...(data !== undefined ? [data] : []));

  if (!REMOTE) return;
  queue.push(event);
  if (queue.length > MAX_QUEUE) queue.shift();
  if (LEVELS[level] >= LEVELS.warn) flush();          // problems go out immediately
  else if (!timer) timer = setTimeout(flush, FLUSH_MS);
}

export const log = {
  debug: (msg, data) => emit('debug', msg, data),
  info: (msg, data) => emit('info', msg, data),
  warn: (msg, data) => emit('warn', msg, data),
  error: (msg, data) => emit('error', msg, data),
};

export const dumpLogs = () => history.slice();

// uncaught errors, rejected promises, and a final flush when the tab closes
export function installGlobalHandlers() {
  if (window.__s2sLoggerInstalled) return;
  window.__s2sLoggerInstalled = true;
  window.__s2sLogs = history;

  window.addEventListener('error', (e) => {
    log.error('Uncaught error', { message: e.message, source: e.filename, line: e.lineno, col: e.colno, stack: e.error?.stack?.slice(0, 600) });
  });
  window.addEventListener('unhandledrejection', (e) => {
    const r = e.reason;
    log.error('Unhandled promise rejection', { message: r?.message || String(r), stack: r?.stack?.slice(0, 600) });
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flush({ beacon: true });
  });
  window.addEventListener('pagehide', () => flush({ beacon: true }));

  log.info('App started', { ua: navigator.userAgent, viewport: `${innerWidth}x${innerHeight}`, mode: import.meta.env.MODE, api: API_BASE });
}
