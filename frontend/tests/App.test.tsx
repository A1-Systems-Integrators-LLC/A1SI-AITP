import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import App from "../src/App";

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App", () => {
  it("renders the sidebar navigation", () => {
    renderApp();
    expect(screen.getByText("CryptoInvestor")).toBeInTheDocument();
    // Nav items also appear as page headings, so use getByRole for nav links
    const nav = screen.getByRole("navigation");
    expect(nav).toHaveTextContent("Dashboard");
    expect(nav).toHaveTextContent("Portfolio");
    expect(nav).toHaveTextContent("Market");
    expect(nav).toHaveTextContent("Trading");
    expect(nav).toHaveTextContent("Settings");
  });
});
