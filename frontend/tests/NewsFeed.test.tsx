import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { NewsFeed } from "../src/components/NewsFeed";
import { renderWithProviders, mockFetch } from "./helpers";

const mockArticles = [
  {
    article_id: "abc123",
    title: "Bitcoin surges to new all-time high",
    url: "https://example.com/article-1",
    source: "CoinDesk",
    summary: "Bitcoin price hits record levels amid institutional buying",
    published_at: new Date(Date.now() - 3600000).toISOString(),
    symbols: ["BTC/USDT"],
    asset_class: "crypto",
    sentiment_score: 0.65,
    sentiment_label: "positive",
    created_at: new Date().toISOString(),
  },
  {
    article_id: "def456",
    title: "Ethereum faces resistance at key level",
    url: "https://example.com/article-2",
    source: "CoinTelegraph",
    summary: "ETH struggles to break through resistance",
    published_at: new Date(Date.now() - 7200000).toISOString(),
    symbols: ["ETH/USDT"],
    asset_class: "crypto",
    sentiment_score: -0.2,
    sentiment_label: "negative",
    created_at: new Date().toISOString(),
  },
];

const mockSentiment = {
  asset_class: "crypto",
  hours: 24,
  total_articles: 10,
  avg_score: 0.25,
  overall_label: "positive",
  positive_count: 5,
  negative_count: 2,
  neutral_count: 3,
};

describe("NewsFeed", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/news/sentiment": mockSentiment,
        "/api/market/news": mockArticles,
      }),
    );
  });

  it("renders the news feed heading", () => {
    renderWithProviders(<NewsFeed />);
    expect(screen.getByText("News Feed")).toBeInTheDocument();
  });

  it("renders the refresh button", () => {
    renderWithProviders(<NewsFeed />);
    const btn = screen.getByTitle("Fetch latest news");
    expect(btn).toBeInTheDocument();
  });

  it("shows article titles after loading", async () => {
    renderWithProviders(<NewsFeed />);
    expect(await screen.findByText("Bitcoin surges to new all-time high")).toBeInTheDocument();
    expect(screen.getByText("Ethereum faces resistance at key level")).toBeInTheDocument();
  });

  it("shows source badges", async () => {
    renderWithProviders(<NewsFeed />);
    expect(await screen.findByText("CoinDesk")).toBeInTheDocument();
    expect(screen.getByText("CoinTelegraph")).toBeInTheDocument();
  });

  it("shows sentiment summary bar", async () => {
    renderWithProviders(<NewsFeed />);
    expect(await screen.findByText("positive")).toBeInTheDocument();
    expect(screen.getByText("5 pos")).toBeInTheDocument();
    expect(screen.getByText("3 neu")).toBeInTheDocument();
    expect(screen.getByText("2 neg")).toBeInTheDocument();
  });

  it("shows empty state when no articles", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/news/sentiment": { ...mockSentiment, total_articles: 0 },
      }),
    );
    renderWithProviders(<NewsFeed />);
    expect(await screen.findByText("No news articles yet")).toBeInTheDocument();
  });

  it("article links open in new tab", async () => {
    renderWithProviders(<NewsFeed />);
    const link = await screen.findByText("Bitcoin surges to new all-time high");
    const anchor = link.closest("a");
    expect(anchor).toHaveAttribute("target", "_blank");
    expect(anchor).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders time ago for articles", async () => {
    renderWithProviders(<NewsFeed />);
    // First article is 1h ago, second is 2h ago
    expect(await screen.findByText("1h ago")).toBeInTheDocument();
    expect(screen.getByText("2h ago")).toBeInTheDocument();
  });
});
