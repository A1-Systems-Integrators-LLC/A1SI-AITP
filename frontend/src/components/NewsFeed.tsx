import { useQuery, useQueryClient } from "@tanstack/react-query";
import { newsApi } from "../api/news";
import { useAssetClass } from "../hooks/useAssetClass";
import type { NewsArticle, SentimentSummary } from "../types";

const SENTIMENT_COLORS = {
  positive: "bg-green-400",
  negative: "bg-red-400",
  neutral: "bg-gray-400",
} as const;

const SENTIMENT_BG = {
  positive: "bg-green-500/10 text-green-400",
  negative: "bg-red-500/10 text-red-400",
  neutral: "bg-gray-500/10 text-gray-400",
} as const;

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function NewsFeed() {
  const queryClient = useQueryClient();
  const { assetClass } = useAssetClass();

  const { data: articles, isLoading: articlesLoading } = useQuery<NewsArticle[]>({
    queryKey: ["news-articles", assetClass],
    queryFn: () => newsApi.list(assetClass, undefined, 10),
    refetchInterval: 60000,
  });

  const { data: sentiment } = useQuery<SentimentSummary>({
    queryKey: ["news-sentiment", assetClass],
    queryFn: () => newsApi.sentiment(assetClass),
    refetchInterval: 60000,
  });

  const handleRefresh = async () => {
    await newsApi.fetch(assetClass);
    queryClient.invalidateQueries({ queryKey: ["news-articles", assetClass] });
    queryClient.invalidateQueries({ queryKey: ["news-sentiment", assetClass] });
  };

  return (
    <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="mb-4 flex items-center gap-3">
        <h3 className="text-lg font-semibold">News Feed</h3>
        <button
          onClick={handleRefresh}
          className="ml-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface)] hover:text-[var(--color-text)]"
          title="Fetch latest news"
        >
          &#8635; Refresh
        </button>
      </div>

      {/* Sentiment Summary Bar */}
      {sentiment && sentiment.total_articles > 0 && (
        <div className="mb-4 flex items-center gap-4 rounded-lg border border-[var(--color-border)] p-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-[var(--color-text-muted)]">Sentiment</span>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${SENTIMENT_BG[sentiment.overall_label]}`}
            >
              {sentiment.overall_label}
            </span>
          </div>
          <span className="text-xs text-[var(--color-text-muted)]">
            Score: {sentiment.avg_score.toFixed(2)}
          </span>
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
            <span className="text-green-400">{sentiment.positive_count} pos</span>
            <span className="text-gray-400">{sentiment.neutral_count} neu</span>
            <span className="text-red-400">{sentiment.negative_count} neg</span>
          </div>
        </div>
      )}

      {/* Article List */}
      {articlesLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-14 animate-pulse rounded-lg bg-[var(--color-border)]" />
          ))}
        </div>
      ) : articles && articles.length > 0 ? (
        <div className="space-y-2">
          {articles.map((article) => (
            <a
              key={article.article_id}
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-start gap-3 rounded-lg border border-[var(--color-border)] p-3 transition-colors hover:bg-[var(--color-bg)]"
            >
              <div
                className={`mt-1.5 h-2.5 w-2.5 flex-shrink-0 rounded-full ${SENTIMENT_COLORS[article.sentiment_label]}`}
                title={`${article.sentiment_label} (${article.sentiment_score.toFixed(2)})`}
              />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium leading-snug">{article.title}</p>
                <div className="mt-1 flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                  <span className="rounded bg-[var(--color-bg)] px-1.5 py-0.5 font-medium">
                    {article.source}
                  </span>
                  <span>{timeAgo(article.published_at)}</span>
                </div>
              </div>
            </a>
          ))}
        </div>
      ) : (
        <div className="py-8 text-center text-sm text-[var(--color-text-muted)]">
          <p>No news articles yet</p>
          <p className="mt-1 text-xs">Click Refresh to fetch the latest news</p>
        </div>
      )}
    </div>
  );
}
