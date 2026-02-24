import { describe, expect, it } from "vitest";
import { getErrorMessage } from "../src/utils/errors";

describe("getErrorMessage", () => {
  it("returns message from Error instance", () => {
    expect(getErrorMessage(new Error("test error"))).toBe("test error");
  });

  it("returns string error directly", () => {
    expect(getErrorMessage("string error")).toBe("string error");
  });

  it("returns fallback for null", () => {
    expect(getErrorMessage(null)).toBe("An unexpected error occurred");
  });

  it("returns fallback for undefined", () => {
    expect(getErrorMessage(undefined)).toBe("An unexpected error occurred");
  });

  it("returns fallback for plain object", () => {
    expect(getErrorMessage({ code: 500 })).toBe("An unexpected error occurred");
  });

  it("returns custom fallback", () => {
    expect(getErrorMessage(42, "Custom fallback")).toBe("Custom fallback");
  });
});
