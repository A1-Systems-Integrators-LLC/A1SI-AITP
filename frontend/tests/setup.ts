import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";

// Restore mocked fetch after each test to prevent Node/undici
// "invalid onError method" errors when vi.stubGlobal("fetch", ...)
// replaces native fetch with an incompatible mock object.
const originalFetch = globalThis.fetch;
afterEach(() => {
  if (globalThis.fetch !== originalFetch) {
    vi.stubGlobal("fetch", originalFetch);
  }
});

// Provide a noop WebSocket so tests that render components using
// useWebSocket (e.g. App, Portfolio) never trigger real connections.
// Prevents Node 20 undici "invalid onError method" errors.
// Tests that need WebSocket behaviour (useWebSocket.test.tsx) override
// this with their own mock in beforeEach/afterEach.
class NoopWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;
  readyState = 3; // CLOSED — no connection attempted
  url: string;
  onopen: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  constructor(url: string) { this.url = url; }
  send() {}
  close() {}
  addEventListener() {}
  removeEventListener() {}
  dispatchEvent() { return false; }
}
vi.stubGlobal("WebSocket", NoopWebSocket);
