import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// We need to test the api client which uses fetch internally
// Import after mocking
let api: typeof import("../src/api/client").api;

describe("API Client", () => {
  const originalFetch = globalThis.fetch;
  const originalLocation = window.location;

  beforeEach(async () => {
    // Reset module cache to get fresh import
    vi.resetModules();
    const mod = await import("../src/api/client");
    api = mod.api;

    // Clear cookies
    Object.defineProperty(document, "cookie", {
      writable: true,
      value: "csrftoken=test-csrf-token",
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    Object.defineProperty(window, "location", {
      writable: true,
      value: originalLocation,
    });
  });

  function mockFetchResponse(overrides: Partial<Response> = {}) {
    const resp = {
      ok: true,
      status: 200,
      statusText: "OK",
      json: () => Promise.resolve({ data: "test" }),
      text: () => Promise.resolve(""),
      ...overrides,
    } as Response;
    globalThis.fetch = vi.fn().mockResolvedValue(resp);
    return globalThis.fetch as ReturnType<typeof vi.fn>;
  }

  describe("GET requests", () => {
    it("sends correct URL with /api prefix", async () => {
      const fetchMock = mockFetchResponse();
      await api.get("/portfolios/");
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/portfolios/",
        expect.objectContaining({ credentials: "include" }),
      );
    });

    it("includes Content-Type header", async () => {
      const fetchMock = mockFetchResponse();
      await api.get("/test/");
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/test/",
        expect.objectContaining({
          headers: expect.objectContaining({
            "Content-Type": "application/json",
          }),
        }),
      );
    });

    it("does not include CSRF token for GET", async () => {
      const fetchMock = mockFetchResponse();
      await api.get("/test/");
      const callHeaders = (fetchMock as ReturnType<typeof vi.fn>).mock
        .calls[0][1].headers;
      expect(callHeaders["X-CSRFToken"]).toBeUndefined();
    });

    it("returns parsed JSON", async () => {
      mockFetchResponse({
        json: () => Promise.resolve({ id: 1, name: "test" }),
      });
      const result = await api.get<{ id: number; name: string }>("/test/");
      expect(result).toEqual({ id: 1, name: "test" });
    });
  });

  describe("POST requests", () => {
    it("includes CSRF token", async () => {
      const fetchMock = mockFetchResponse();
      await api.post("/test/", { foo: "bar" });
      const callHeaders = (fetchMock as ReturnType<typeof vi.fn>).mock
        .calls[0][1].headers;
      expect(callHeaders["X-CSRFToken"]).toBe("test-csrf-token");
    });

    it("sends JSON body", async () => {
      const fetchMock = mockFetchResponse();
      await api.post("/test/", { foo: "bar" });
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/test/",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ foo: "bar" }),
        }),
      );
    });

    it("handles POST with no body", async () => {
      const fetchMock = mockFetchResponse();
      await api.post("/test/");
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/test/",
        expect.objectContaining({
          method: "POST",
          body: undefined,
        }),
      );
    });
  });

  describe("PUT requests", () => {
    it("includes CSRF token and body", async () => {
      const fetchMock = mockFetchResponse();
      await api.put("/test/1/", { name: "updated" });
      const call = (fetchMock as ReturnType<typeof vi.fn>).mock.calls[0][1];
      expect(call.method).toBe("PUT");
      expect(call.headers["X-CSRFToken"]).toBe("test-csrf-token");
      expect(call.body).toBe(JSON.stringify({ name: "updated" }));
    });
  });

  describe("PATCH requests", () => {
    it("sends PATCH method with CSRF", async () => {
      const fetchMock = mockFetchResponse();
      await api.patch("/test/1/", { name: "patched" });
      const call = (fetchMock as ReturnType<typeof vi.fn>).mock.calls[0][1];
      expect(call.method).toBe("PATCH");
      expect(call.headers["X-CSRFToken"]).toBe("test-csrf-token");
    });
  });

  describe("DELETE requests", () => {
    it("sends DELETE method with CSRF", async () => {
      const fetchMock = mockFetchResponse();
      await api.delete("/test/1/");
      const call = (fetchMock as ReturnType<typeof vi.fn>).mock.calls[0][1];
      expect(call.method).toBe("DELETE");
      expect(call.headers["X-CSRFToken"]).toBe("test-csrf-token");
    });
  });

  describe("error handling", () => {
    it("redirects to /login on 401", async () => {
      mockFetchResponse({ ok: false, status: 401, statusText: "Unauthorized" });

      const hrefSetter = vi.fn();
      Object.defineProperty(window, "location", {
        writable: true,
        value: {
          ...originalLocation,
          pathname: "/dashboard",
          get href() {
            return "";
          },
          set href(v: string) {
            hrefSetter(v);
          },
        },
      });

      await expect(api.get("/test/")).rejects.toThrow("Unauthorized");
      expect(hrefSetter).toHaveBeenCalledWith("/login");
    });

    it("does not redirect if already on login page", async () => {
      mockFetchResponse({ ok: false, status: 401, statusText: "Unauthorized" });

      const hrefSetter = vi.fn();
      Object.defineProperty(window, "location", {
        writable: true,
        value: {
          ...originalLocation,
          pathname: "/login",
          get href() {
            return "";
          },
          set href(v: string) {
            hrefSetter(v);
          },
        },
      });

      await expect(api.get("/test/")).rejects.toThrow("Unauthorized");
      expect(hrefSetter).not.toHaveBeenCalled();
    });

    it("throws CSRF error on 403 with CSRF body", async () => {
      mockFetchResponse({
        ok: false,
        status: 403,
        statusText: "Forbidden",
        text: () => Promise.resolve("CSRF verification failed"),
      });

      await expect(api.post("/test/", {})).rejects.toThrow(
        "CSRF validation failed",
      );
    });

    it("throws Forbidden on 403 without CSRF", async () => {
      mockFetchResponse({
        ok: false,
        status: 403,
        statusText: "Forbidden",
        text: () => Promise.resolve("Permission denied"),
      });

      await expect(api.post("/test/", {})).rejects.toThrow("Forbidden");
    });

    it("throws ApiError on other non-OK statuses", async () => {
      mockFetchResponse({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: () => Promise.reject(new Error("not json")),
      });

      await expect(api.get("/test/")).rejects.toThrow(
        "API error: 500 Internal Server Error",
      );
    });

    it("throws ApiError with parsed JSON body", async () => {
      mockFetchResponse({
        ok: false,
        status: 400,
        statusText: "Bad Request",
        json: () => Promise.resolve({ error: "Symbol too short", symbol: ["Minimum 5 characters"] }),
      });

      try {
        await api.get("/test/");
        expect.fail("should have thrown");
      } catch (err) {
        const { ApiError: ApiErrorClass } = await import("../src/api/client");
        expect(err).toBeInstanceOf(ApiErrorClass);
        expect((err as InstanceType<typeof ApiErrorClass>).status).toBe(400);
        expect((err as InstanceType<typeof ApiErrorClass>).message).toBe("Symbol too short");
      }
    });

    it("ApiError fieldErrors parses DRF format", async () => {
      mockFetchResponse({
        ok: false,
        status: 400,
        statusText: "Bad Request",
        json: () => Promise.resolve({ symbol: ["Too short"], amount: ["Required"] }),
      });

      try {
        await api.get("/test/");
        expect.fail("should have thrown");
      } catch (err) {
        const { ApiError: ApiErrorClass } = await import("../src/api/client");
        expect(err).toBeInstanceOf(ApiErrorClass);
        const fieldErrors = (err as InstanceType<typeof ApiErrorClass>).fieldErrors;
        expect(fieldErrors.symbol).toBe("Too short");
        expect(fieldErrors.amount).toBe("Required");
      }
    });

    it("ApiError fieldErrors parses string values", async () => {
      mockFetchResponse({
        ok: false,
        status: 400,
        statusText: "Bad Request",
        json: () => Promise.resolve({ name: "This field is required." }),
      });

      try {
        await api.get("/test/");
        expect.fail("should have thrown");
      } catch (err) {
        const { ApiError: ApiErrorClass } = await import("../src/api/client");
        expect(err).toBeInstanceOf(ApiErrorClass);
        const fieldErrors = (err as InstanceType<typeof ApiErrorClass>).fieldErrors;
        expect(fieldErrors.name).toBe("This field is required.");
      }
    });

    it("ApiError fieldErrors empty for non-object body", async () => {
      mockFetchResponse({
        ok: false,
        status: 400,
        statusText: "Bad Request",
        json: () => Promise.reject(new Error("not json")),
      });

      try {
        await api.get("/test/");
        expect.fail("should have thrown");
      } catch (err) {
        const { ApiError: ApiErrorClass } = await import("../src/api/client");
        expect(err).toBeInstanceOf(ApiErrorClass);
        expect((err as InstanceType<typeof ApiErrorClass>).fieldErrors).toEqual({});
      }
    });

    it("ApiError falls back to status text when no error field", async () => {
      mockFetchResponse({
        ok: false,
        status: 422,
        statusText: "Unprocessable Entity",
        json: () => Promise.resolve({ detail: "Validation error" }),
      });

      try {
        await api.get("/test/");
        expect.fail("should have thrown");
      } catch (err) {
        const { ApiError } = await import("../src/api/client");
        expect(err).toBeInstanceOf(ApiError);
        expect((err as InstanceType<typeof ApiError>).message).toBe("API error: 422 Unprocessable Entity");
      }
    });

    it("non-JSON error response still throws ApiError", async () => {
      mockFetchResponse({
        ok: false,
        status: 502,
        statusText: "Bad Gateway",
        json: () => Promise.reject(new Error("not json")),
      });

      try {
        await api.get("/test/");
        expect.fail("should have thrown");
      } catch (err) {
        const { ApiError: ApiErrorClass } = await import("../src/api/client");
        expect(err).toBeInstanceOf(ApiErrorClass);
        expect((err as InstanceType<typeof ApiErrorClass>).body).toBeNull();
      }
    });

    it("returns undefined for 204 No Content", async () => {
      mockFetchResponse({ status: 204 });
      const result = await api.delete("/test/1/");
      expect(result).toBeUndefined();
    });
  });

  describe("CSRF token parsing", () => {
    it("sends empty string when no csrf cookie", async () => {
      Object.defineProperty(document, "cookie", {
        writable: true,
        value: "other=value",
      });

      const fetchMock = mockFetchResponse();
      await api.post("/test/", {});
      const callHeaders = (fetchMock as ReturnType<typeof vi.fn>).mock
        .calls[0][1].headers;
      expect(callHeaders["X-CSRFToken"]).toBe("");
    });
  });
});
