import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { useAssetClass } from "../src/hooks/useAssetClass";
import { AssetClassContext } from "../src/contexts/assetClass";
import type { ReactNode } from "react";

describe("useAssetClass", () => {
  it("returns default context value", () => {
    const { result } = renderHook(() => useAssetClass());
    expect(result.current.assetClass).toBe("crypto");
  });

  it("returns provided context value", () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <AssetClassContext.Provider value={{ assetClass: "equity", setAssetClass: () => {} }}>
        {children}
      </AssetClassContext.Provider>
    );
    const { result } = renderHook(() => useAssetClass(), { wrapper });
    expect(result.current.assetClass).toBe("equity");
  });
});
