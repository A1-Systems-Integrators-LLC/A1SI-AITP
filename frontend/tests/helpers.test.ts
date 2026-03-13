import { describe, it, expect } from "vitest";
import { mockFetch } from "./helpers";

describe("mockFetch", () => {
  it("rejects unhandled non-API URLs", async () => {
    const fetch = mockFetch({});
    await expect(fetch("https://external.com/data")).rejects.toThrow(
      "Unhandled fetch: https://external.com/data",
    );
  });

  it("returns empty array for unmatched GET /api/ calls", async () => {
    const fetch = mockFetch({});
    const res = await fetch("/api/unknown/");
    const data = await res.json();
    expect(data).toEqual([]);
  });

  it("returns empty object for unmatched POST /api/ calls", async () => {
    const fetch = mockFetch({});
    const res = await fetch("/api/unknown/", { method: "POST" });
    const data = await res.json();
    expect(data).toEqual({});
  });
});
