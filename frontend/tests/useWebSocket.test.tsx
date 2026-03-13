import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWebSocket } from "../src/hooks/useWebSocket";

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;

  url: string;
  readyState: number = 0; // CONNECTING
  onopen: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  send = vi.fn();
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  simulateOpen() {
    this.readyState = 1; // OPEN
    this.onopen?.(new Event("open"));
  }

  simulateMessage(data: unknown) {
    this.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify(data) }),
    );
  }

  simulateClose() {
    this.readyState = 3; // CLOSED
    this.onclose?.(new CloseEvent("close"));
  }

  simulateError() {
    this.onerror?.(new Event("error"));
  }
}

describe("useWebSocket", () => {
  const OriginalWebSocket = globalThis.WebSocket;

  beforeEach(() => {
    MockWebSocket.instances = [];
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    vi.useFakeTimers();
  });

  afterEach(() => {
    globalThis.WebSocket = OriginalWebSocket;
    vi.useRealTimers();
  });

  it("connects to correct URL using current protocol", () => {
    renderHook(() => useWebSocket("/ws/test/"));

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toContain("/ws/test/");
  });

  it("sets isConnected to true on open", () => {
    const { result } = renderHook(() => useWebSocket("/ws/test/"));

    expect(result.current.isConnected).toBe(false);

    act(() => {
      MockWebSocket.instances[0].simulateOpen();
    });

    expect(result.current.isConnected).toBe(true);
  });

  it("sets isConnected to false on close", () => {
    const { result } = renderHook(() =>
      useWebSocket("/ws/test/", { reconnect: false }),
    );

    act(() => {
      MockWebSocket.instances[0].simulateOpen();
    });
    expect(result.current.isConnected).toBe(true);

    act(() => {
      MockWebSocket.instances[0].simulateClose();
    });
    expect(result.current.isConnected).toBe(false);
  });

  it("updates lastMessage on incoming message", () => {
    const { result } = renderHook(() =>
      useWebSocket<{ type: string }>("/ws/test/"),
    );

    act(() => {
      MockWebSocket.instances[0].simulateOpen();
      MockWebSocket.instances[0].simulateMessage({ type: "hello" });
    });

    expect(result.current.lastMessage).toEqual({ type: "hello" });
  });

  it("ignores non-JSON messages", () => {
    const { result } = renderHook(() => useWebSocket("/ws/test/"));

    act(() => {
      MockWebSocket.instances[0].simulateOpen();
      // Send raw non-JSON message
      MockWebSocket.instances[0].onmessage?.(
        new MessageEvent("message", { data: "not json" }),
      );
    });

    expect(result.current.lastMessage).toBeNull();
  });

  it("send() calls ws.send with JSON", () => {
    const { result } = renderHook(() => useWebSocket("/ws/test/"));

    act(() => {
      MockWebSocket.instances[0].simulateOpen();
    });

    act(() => {
      result.current.send({ action: "subscribe" });
    });

    expect(MockWebSocket.instances[0].send).toHaveBeenCalledWith(
      JSON.stringify({ action: "subscribe" }),
    );
  });

  it("send() does nothing when not connected", () => {
    const { result } = renderHook(() =>
      useWebSocket("/ws/test/", { reconnect: false }),
    );

    // Before open, readyState is CONNECTING so send should be a no-op.
    // The hook won't call ws.send because readyState !== OPEN.
    // We verify by checking that after calling send, the mock's send count
    // stays at 0. But the ws ref is still set (not null) — it just isn't OPEN.
    // Our mock starts with readyState=CONNECTING which is not OPEN.
    // However the mock WebSocket constructor initializes readyState to
    // WebSocket.CONNECTING (0), and the hook checks WebSocket.OPEN (1).
    // But in our mock, WebSocket.CONNECTING may not equal the global constant.
    // Let's verify the hook's behavior: open, then close, then send should no-op.

    act(() => {
      MockWebSocket.instances[0].simulateOpen();
    });

    // Now close — the hook sets wsRef.current = null
    act(() => {
      MockWebSocket.instances[0].simulateClose();
    });

    // send should silently do nothing since wsRef.current is null
    act(() => {
      result.current.send({ action: "subscribe" });
    });

    // The original instance's send was never called
    // (it was only called during open state if we had called send then)
    expect(MockWebSocket.instances[0].send).not.toHaveBeenCalled();
  });

  it("reconnects with exponential backoff", () => {
    renderHook(() =>
      useWebSocket("/ws/test/", { reconnect: true, maxReconnectDelay: 10000 }),
    );

    expect(MockWebSocket.instances).toHaveLength(1);

    // First close → reconnect after 1s
    act(() => {
      MockWebSocket.instances[0].simulateClose();
    });
    expect(MockWebSocket.instances).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(MockWebSocket.instances).toHaveLength(2);

    // Second close → reconnect after 2s
    act(() => {
      MockWebSocket.instances[1].simulateClose();
    });

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(MockWebSocket.instances).toHaveLength(2); // not yet

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(MockWebSocket.instances).toHaveLength(3); // after 2s total
  });

  it("resets reconnect counter on successful connection", () => {
    renderHook(() => useWebSocket("/ws/test/", { reconnect: true }));

    // Close and reconnect
    act(() => {
      MockWebSocket.instances[0].simulateClose();
      vi.advanceTimersByTime(1000);
    });
    expect(MockWebSocket.instances).toHaveLength(2);

    // Open successfully, then close again
    act(() => {
      MockWebSocket.instances[1].simulateOpen();
      MockWebSocket.instances[1].simulateClose();
    });

    // Should reconnect after 1s (reset backoff)
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(MockWebSocket.instances).toHaveLength(3);
  });

  it("does not reconnect when reconnect is false", () => {
    renderHook(() => useWebSocket("/ws/test/", { reconnect: false }));

    act(() => {
      MockWebSocket.instances[0].simulateClose();
      vi.advanceTimersByTime(5000);
    });

    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("caps reconnect delay at maxReconnectDelay", () => {
    renderHook(() =>
      useWebSocket("/ws/test/", {
        reconnect: true,
        maxReconnectDelay: 4000,
      }),
    );

    // Close 5 times to ramp up backoff: 1s, 2s, 4s, 4s (capped), 4s
    for (let i = 0; i < 5; i++) {
      act(() => {
        MockWebSocket.instances[MockWebSocket.instances.length - 1].simulateClose();
        // Advance past max delay to ensure reconnect
        vi.advanceTimersByTime(4000);
      });
    }

    // Should have created 6 instances total (1 initial + 5 reconnects)
    expect(MockWebSocket.instances).toHaveLength(6);
  });

  it("cleans up on unmount", () => {
    const { unmount } = renderHook(() => useWebSocket("/ws/test/"));

    act(() => {
      MockWebSocket.instances[0].simulateOpen();
    });

    unmount();

    expect(MockWebSocket.instances[0].close).toHaveBeenCalled();
  });

  it("closes socket if unmounted during onopen", () => {
    const { unmount } = renderHook(() =>
      useWebSocket("/ws/test/", { reconnect: false }),
    );

    // Unmount before the socket opens
    unmount();

    // Now trigger onopen — the hook should close the socket immediately
    act(() => {
      MockWebSocket.instances[0].simulateOpen();
    });

    expect(MockWebSocket.instances[0].close).toHaveBeenCalled();
  });

  it("manual reconnect resets state and reconnects", () => {
    const { result } = renderHook(() => useWebSocket("/ws/test/"));

    // Open then close to create a reconnect attempt
    act(() => {
      MockWebSocket.instances[0].simulateOpen();
    });

    // Call manual reconnect
    act(() => {
      result.current.reconnect();
    });

    // Should have created a new WebSocket (the reconnect call invokes connect)
    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2);
  });

  it("does not reconnect after unmount", () => {
    const { unmount } = renderHook(() =>
      useWebSocket("/ws/test/", { reconnect: true }),
    );

    unmount();

    act(() => {
      MockWebSocket.instances[0].simulateClose();
      vi.advanceTimersByTime(5000);
    });

    expect(MockWebSocket.instances).toHaveLength(1);
  });
});
