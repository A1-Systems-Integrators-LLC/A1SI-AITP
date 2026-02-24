import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AssetClassBadge } from "../src/components/AssetClassBadge";

describe("AssetClassBadge", () => {
  it("renders Crypto label with orange color", () => {
    render(<AssetClassBadge assetClass="crypto" />);
    const badge = screen.getByText("Crypto");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("orange");
  });

  it("renders Equities label with blue color", () => {
    render(<AssetClassBadge assetClass="equity" />);
    const badge = screen.getByText("Equities");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("blue");
  });

  it("renders Forex label with green color", () => {
    render(<AssetClassBadge assetClass="forex" />);
    const badge = screen.getByText("Forex");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("green");
  });
});
