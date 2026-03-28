import { Newspaper, ExternalLink, Bookmark, Clock, TrendingUp, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

const tabs = ["All", "Tech", "Business", "World", "Science"];

const articles = [
  {
    id: "1",
    title: "OpenAI Announces GPT-5 with Real-Time Reasoning Capabilities",
    source: "TechCrunch",
    time: "2h ago",
    summary: "The new model demonstrates significant improvements in multi-step reasoning and tool use, with benchmark scores surpassing previous generations by 40%.",
    topic: "Tech",
    imageColor: "from-blue-600 to-violet-600",
    relevance: 95,
  },
  {
    id: "2",
    title: "Stripe Launches AI-Powered Invoice Processing for SMBs",
    source: "The Verge",
    time: "4h ago",
    summary: "New feature automatically extracts line items, matches them to purchase orders, and flags discrepancies — reducing manual reconciliation by 80%.",
    topic: "Business",
    imageColor: "from-emerald-600 to-teal-600",
    relevance: 88,
  },
  {
    id: "3",
    title: "TypeScript 6.0 Released with Native Pattern Matching",
    source: "Hacker News",
    time: "5h ago",
    summary: "Major release includes native pattern matching, improved type inference, and 30% faster compilation times across large codebases.",
    topic: "Tech",
    imageColor: "from-cyan-600 to-blue-600",
    relevance: 92,
  },
  {
    id: "4",
    title: "Federal Reserve Signals Potential Rate Cut in Q3 2026",
    source: "Reuters",
    time: "6h ago",
    summary: "Fed Chair indicates softening inflation data may warrant action, sending markets up 1.5% in afternoon trading.",
    topic: "Business",
    imageColor: "from-orange-600 to-red-600",
    relevance: 71,
  },
  {
    id: "5",
    title: "SpaceX Successfully Tests Starship Heat Shield Improvements",
    source: "Ars Technica",
    time: "8h ago",
    summary: "Latest test flight demonstrated zero tile damage during re-entry, marking a critical milestone for the Mars transport system.",
    topic: "Science",
    imageColor: "from-purple-600 to-pink-600",
    relevance: 76,
  },
  {
    id: "6",
    title: "Docker Acquires Cloud IDE Startup for $200M",
    source: "TechCrunch",
    time: "10h ago",
    summary: "Acquisition aims to integrate browser-based development environments directly into Docker Desktop, challenging GitHub Codespaces.",
    topic: "Tech",
    imageColor: "from-indigo-600 to-blue-600",
    relevance: 85,
  },
];

export function NewsPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Your News Feed</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            AI-curated from your sources · Updated 15 min ago
          </p>
        </div>
        <button className="flex items-center gap-2 h-9 px-4 rounded-lg border border-border bg-card text-sm text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors">
          <Sparkles className="h-4 w-4" />
          Manage Sources
        </button>
      </div>

      {/* Topic tabs */}
      <div className="flex gap-2">
        {tabs.map((tab, i) => (
          <button
            key={tab}
            className={cn(
              "px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors",
              i === 0
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-muted-foreground hover:text-foreground",
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Articles grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {articles.map((article) => (
          <div
            key={article.id}
            className="group rounded-xl border border-border bg-card overflow-hidden hover:border-primary/20 transition-colors cursor-pointer"
          >
            {/* Color banner (placeholder for image) */}
            <div className={cn("h-32 bg-gradient-to-br", article.imageColor)} />

            <div className="p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] uppercase tracking-wider font-semibold text-primary">
                    {article.topic}
                  </span>
                  <span className="text-muted-foreground">·</span>
                  <span className="text-xs text-muted-foreground">{article.source}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Bookmark className="h-3.5 w-3.5 text-muted-foreground/40 hover:text-foreground transition-colors" />
                  <ExternalLink className="h-3.5 w-3.5 text-muted-foreground/40 hover:text-foreground transition-colors" />
                </div>
              </div>

              <h3 className="text-sm font-semibold text-foreground leading-snug line-clamp-2 group-hover:text-primary transition-colors">
                {article.title}
              </h3>

              <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
                {article.summary}
              </p>

              <div className="flex items-center justify-between pt-1">
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  {article.time}
                </span>
                <span className="flex items-center gap-1 text-[11px] text-success">
                  <TrendingUp className="h-3 w-3" />
                  {article.relevance}% relevant
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
        <Newspaper className="h-4 w-4" />
        <span>Add RSS feeds, NewsAPI sources, or Hacker News in Settings</span>
      </div>
    </div>
  );
}
