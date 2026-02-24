import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent, render } from "@testing-library/react";
import { AssetClassSelector } from "../src/components/AssetClassSelector";
import { AssetClassContext } from "../src/contexts/assetClass";

function renderSelector(assetClass = "crypto" as "crypto" | "equity" | "forex") {
  const setAssetClass = vi.fn();
  render(
    <AssetClassContext.Provider value={{ assetClass, setAssetClass }}>
      <AssetClassSelector />
    </AssetClassContext.Provider>,
  );
  return { setAssetClass };
}

describe("AssetClassSelector", () => {
  it("renders three segments", () => {
    renderSelector();
    expect(screen.getByText("Crypto")).toBeInTheDocument();
    expect(screen.getByText("Equities")).toBeInTheDocument();
    expect(screen.getByText("Forex")).toBeInTheDocument();
  });

  it("highlights active asset class", () => {
    renderSelector("equity");
    const btn = screen.getByText("Equities").closest("button")!;
    expect(btn.className).toContain("primary");
  });

  it("calls setAssetClass on click", () => {
    const { setAssetClass } = renderSelector("crypto");
    fireEvent.click(screen.getByText("Forex"));
    expect(setAssetClass).toHaveBeenCalledWith("forex");
  });

  it("shows correct labels", () => {
    renderSelector();
    expect(screen.getByText("Crypto")).toBeInTheDocument();
    expect(screen.getByText("Equities")).toBeInTheDocument();
    expect(screen.getByText("Forex")).toBeInTheDocument();
  });
});
