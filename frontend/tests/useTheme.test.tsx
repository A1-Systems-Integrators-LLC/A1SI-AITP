import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { useTheme } from "../src/hooks/useTheme";
import { ThemeContext } from "../src/contexts/theme";
import type { ReactNode } from "react";

describe("useTheme", () => {
  it("returns default context value", () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("dark");
  });

  it("returns provided context value", () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <ThemeContext.Provider value={{ theme: "light", setTheme: () => {} }}>
        {children}
      </ThemeContext.Provider>
    );
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.theme).toBe("light");
  });
});
