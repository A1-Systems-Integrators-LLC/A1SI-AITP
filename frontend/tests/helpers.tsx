import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ToastProvider } from "../src/components/Toast";

export function renderWithProviders(
  ui: ReactElement,
  { route = "/" }: { route?: string } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <ToastProvider>{ui}</ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/**
 * Build a real Response returning JSON data so Node 20's undici
 * does not throw "invalid onError method" on cleanup.
 */
function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Mock fetch to return JSON data for matching URL patterns.
 * Returns empty array/object for unmatched routes.
 */
export function mockFetch(handlers: Record<string, unknown>) {
  const mockFn = (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();

    for (const [pattern, data] of Object.entries(handlers)) {
      if (url.includes(pattern)) {
        return Promise.resolve(jsonResponse(data));
      }
    }

    // Default: return empty response for unmatched API calls
    if (url.startsWith("/api/")) {
      const isPost = init?.method === "POST";
      return Promise.resolve(jsonResponse(isPost ? {} : []));
    }

    return Promise.reject(new Error(`Unhandled fetch: ${url}`));
  };

  return mockFn as typeof globalThis.fetch;
}
