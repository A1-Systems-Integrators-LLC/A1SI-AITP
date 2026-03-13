import { describe, expect, it } from "vitest";
import { formatPrice, formatVolume } from "../src/utils/formatters";

describe("formatPrice", () => {
  it("formats crypto price with dollar sign", () => {
    expect(formatPrice(50000.5, "crypto")).toMatch(/\$50,000\.50/);
  });

  it("formats forex price with 5 decimals", () => {
    expect(formatPrice(1.23456, "forex")).toBe("1.23456");
  });

  it("formats sub-dollar crypto price with 6 decimals", () => {
    expect(formatPrice(0.00123, "crypto")).toBe("0.001230");
  });
});

describe("formatVolume", () => {
  it("formats billions", () => {
    expect(formatVolume(2_500_000_000)).toBe("2.5B");
  });

  it("formats millions", () => {
    expect(formatVolume(3_400_000)).toBe("3.4M");
  });

  it("formats thousands", () => {
    expect(formatVolume(1_500)).toBe("1.5K");
  });

  it("formats raw numbers below 1000", () => {
    expect(formatVolume(500)).toBe("500");
  });
});
