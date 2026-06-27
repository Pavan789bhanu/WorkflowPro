/**
 * Resolve API and WebSocket base URLs.
 *
 * - Local dev:           VITE_API_URL=http://localhost:8000 (from .env)
 * - Docker / production: VITE_API_URL=""  → same-origin relative requests,
 *                        nginx proxies /api and /ws to the backend container.
 * - Unset:               falls back to http://localhost:8000
 */

const rawApi = import.meta.env.VITE_API_URL as string | undefined;
const rawWs = import.meta.env.VITE_WS_URL as string | undefined;

/** Base URL for HTTP API calls ('' = same origin). */
export const API_BASE: string = rawApi !== undefined ? rawApi : 'http://localhost:8000';

/** Base URL for WebSocket connections. */
export function getWsBase(): string {
  if (rawWs !== undefined && rawWs !== '') return rawWs;
  if (rawWs === '' && typeof window !== 'undefined') {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}`;
  }
  return 'ws://localhost:8000';
}
