import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Routes, Route } from "react-router-dom";
import App from "../src/App";
import { Layout } from "../src/components/Layout";
import { renderWithProviders, mockFetch } from "./helpers";

const authHandlers = {
  "/api/auth/status/": { authenticated: true, username: "testuser" },
};

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch(authHandlers));
});

describe("App", () => {
  it("renders the sidebar navigation", async () => {
    renderWithProviders(<App />);
    await waitFor(() => {
      expect(screen.getByText("CryptoInvestor")).toBeInTheDocument();
    });
    const nav = screen.getByRole("navigation");
    expect(nav).toHaveTextContent("Dashboard");
    expect(nav).toHaveTextContent("Portfolio");
    expect(nav).toHaveTextContent("Market");
    expect(nav).toHaveTextContent("Trading");
    expect(nav).toHaveTextContent("Settings");
  });

  it("renders new nav items from Sprint 3 and 4", async () => {
    renderWithProviders(<App />);
    await waitFor(() => {
      expect(screen.getByRole("navigation")).toBeInTheDocument();
    });
    const nav = screen.getByRole("navigation");
    expect(nav).toHaveTextContent("Regime");
    expect(nav).toHaveTextContent("Paper Trade");
  });

  it("renders all 11 navigation items", async () => {
    renderWithProviders(<App />);
    await waitFor(() => {
      expect(screen.getByRole("navigation")).toBeInTheDocument();
    });
    const nav = screen.getByRole("navigation");
    const links = nav.querySelectorAll("a");
    expect(links.length).toBe(11);
  });
});

describe("Layout", () => {
  it("renders outlet content", () => {
    renderWithProviders(
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<div>Test Content</div>} />
        </Route>
      </Routes>,
    );
    expect(screen.getByText("Test Content")).toBeInTheDocument();
  });
});
