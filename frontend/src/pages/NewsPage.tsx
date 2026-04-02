import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Bookmark,
  BookmarkCheck,
  ExternalLink,
  Loader2,
  Newspaper,
  Plus,
  RefreshCw,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";

import {
  ApiError,
  bookmarkNewsArticle,
  createNewsSource,
  deleteNewsSource,
  fetchNewsNow,
  listNewsArticles,
  listNewsBookmarks,
  listNewsSources,
  unbookmarkNewsArticle,
} from "@/lib/api";
import type { NewsArticle, NewsSourceRead } from "@/types";

const tabs = ["all", "tech", "business", "world", "science"];

export function NewsPage() {
  const [activeTab, setActiveTab] = useState("all");
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [sources, setSources] = useState<NewsSourceRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);

  const [sourceName, setSourceName] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceTopic, setSourceTopic] = useState("all");
  const [addingSource, setAddingSource] = useState(false);

  const loadNews = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [articlesRes, sourcesRes, bookmarksRes] = await Promise.all([
        listNewsArticles({ topic: activeTab, limit: 30 }),
        listNewsSources(),
        listNewsBookmarks(),
      ]);

      const bookmarked = new Set(bookmarksRes.bookmarks.map((b) => b.article_id));
      setArticles(
        articlesRes.articles.map((a) => ({
          ...a,
          is_bookmarked: bookmarked.has(a.id),
        })),
      );
      setSources(sourcesRes.sources);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load news.";
      setError(message);
      setArticles([]);
      setSources([]);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    void loadNews();
  }, [loadNews]);

  const handleFetchNow = async () => {
    setFetching(true);
    try {
      await fetchNewsNow();
      await loadNews();
    } finally {
      setFetching(false);
    }
  };

  const handleAddSource = async (e: FormEvent) => {
    e.preventDefault();
    if (!sourceName.trim()) return;

    setAddingSource(true);
    setError(null);
    try {
      await createNewsSource({
        source_type: "rss",
        name: sourceName.trim(),
        url: sourceUrl.trim() || undefined,
        topic: sourceTopic,
        enabled: true,
      });
      setSourceName("");
      setSourceUrl("");
      setSourceTopic("all");
      await loadNews();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to add source.";
      setError(message);
    } finally {
      setAddingSource(false);
    }
  };

  const handleDeleteSource = async (sourceId: string) => {
    try {
      await deleteNewsSource(sourceId);
      await loadNews();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to delete source.";
      setError(message);
    }
  };

  const handleToggleBookmark = async (article: NewsArticle) => {
    try {
      if (article.is_bookmarked) {
        await unbookmarkNewsArticle(article.id);
      } else {
        await bookmarkNewsArticle(article.id);
      }
      setArticles((prev) =>
        prev.map((item) =>
          item.id === article.id ? { ...item, is_bookmarked: !item.is_bookmarked } : item,
        ),
      );
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to update bookmark.";
      setError(message);
    }
  };

  const subtitle = useMemo(() => {
    if (loading) return "Refreshing latest stories...";
    return `${articles.length} stories from ${sources.length} configured sources`;
  }, [loading, articles.length, sources.length]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">AI-Curated News</h2>
          <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>
        </div>
        <button
          onClick={() => void handleFetchNow()}
          className="flex items-center gap-2 h-9 px-4 rounded-lg border border-border bg-card text-sm text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
        >
          {fetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Fetch Now
        </button>
      </div>

      <div className="flex gap-2 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors whitespace-nowrap ${
              tab === activeTab
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab[0].toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/[0.08] px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[2fr,1fr] gap-4">
        <div className="rounded-xl border border-border bg-card p-4">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : articles.length === 0 ? (
            <div className="py-20 text-center text-sm text-muted-foreground">No stories for this topic.</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {articles.map((article) => (
                <div key={article.id} className="rounded-xl border border-border bg-secondary/20 p-4 space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[10px] uppercase tracking-wider text-primary">{article.topic}</p>
                      <h3 className="text-sm font-semibold text-foreground line-clamp-2 mt-1">{article.title}</h3>
                    </div>
                    <button
                      onClick={() => void handleToggleBookmark(article)}
                      className="text-muted-foreground hover:text-foreground"
                      title={article.is_bookmarked ? "Remove bookmark" : "Save for later"}
                    >
                      {article.is_bookmarked ? <BookmarkCheck className="h-4 w-4 text-primary" /> : <Bookmark className="h-4 w-4" />}
                    </button>
                  </div>

                  {article.summary && (
                    <p className="text-xs text-muted-foreground line-clamp-3">{article.summary}</p>
                  )}

                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-muted-foreground">
                      {article.source} - {article.published_at ? formatDistanceToNow(new Date(article.published_at), { addSuffix: true }) : "recent"}
                    </span>
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-muted-foreground hover:text-foreground"
                      title="Open article"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-card p-4 space-y-3">
            <h3 className="text-sm font-semibold text-foreground">News Sources</h3>
            <form onSubmit={handleAddSource} className="space-y-2">
              <input
                value={sourceName}
                onChange={(e) => setSourceName(e.target.value)}
                placeholder="Source name"
                className="h-9 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground"
              />
              <input
                value={sourceUrl}
                onChange={(e) => setSourceUrl(e.target.value)}
                placeholder="RSS URL (optional)"
                className="h-9 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground"
              />
              <select
                value={sourceTopic}
                onChange={(e) => setSourceTopic(e.target.value)}
                className="h-9 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground"
              >
                {tabs.map((tab) => (
                  <option key={tab} value={tab}>
                    {tab[0].toUpperCase() + tab.slice(1)}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                disabled={addingSource}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 disabled:opacity-50"
              >
                {addingSource ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                Add Source
              </button>
            </form>

            <div className="space-y-2 max-h-[260px] overflow-y-auto">
              {sources.map((source) => (
                <div key={source.id} className="rounded-lg border border-border/60 bg-secondary/20 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs text-foreground font-medium truncate">{source.name}</p>
                    {source.source_type === "rss" && (
                      <button
                        onClick={() => void handleDeleteSource(source.id)}
                        className="text-[10px] text-destructive hover:underline"
                      >
                        Remove
                      </button>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground">{source.source_type} - {source.topic}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Newspaper className="h-4 w-4" />
              <span>Bookmarks feed into your morning digest.</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
