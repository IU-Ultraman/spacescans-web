"use client";

import { useEffect, useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Loader2, Search } from "lucide-react";
import { cn } from "@/lib/utils";

interface SearchItem {
  id: string;
  label: string;
  definition: string;
}

interface OntologySearchProps {
  onSelect: (id: string) => void;
}

export function OntologySearch({ onSelect }: OntologySearchProps) {
  const [index, setIndex] = useState<SearchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  useEffect(() => {
    fetch("/ontology/search-index.json")
      .then((r) => r.json())
      .then((data: SearchItem[]) => setIndex(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const results = useMemo(() => {
    if (!query.trim()) return [];
    const q = query.toLowerCase();
    return index
      .filter(
        (item) =>
          item.label.toLowerCase().includes(q) ||
          item.definition.toLowerCase().includes(q)
      )
      .slice(0, 20);
  }, [query, index]);

  return (
    <div className="space-y-2">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground/50" />
        <Input
          placeholder="Search variables..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="pl-9"
          disabled={loading}
        />
        {loading && (
          <Loader2 className="absolute right-2.5 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground/50" />
        )}
      </div>

      {results.length > 0 && (
        <div className="max-h-52 overflow-y-auto rounded-lg border border-border bg-background shadow-sm">
          {results.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => {
                onSelect(item.id);
                setQuery("");
              }}
              className={cn(
                "flex w-full flex-col gap-0.5 px-3 py-2 text-left transition-colors hover:bg-muted/60",
                "border-b border-border/50 last:border-b-0"
              )}
            >
              <span className="text-sm font-medium text-foreground">
                {item.label.replace(/_/g, " ")}
              </span>
              {item.definition && (
                <span className="line-clamp-1 text-xs text-muted-foreground">
                  {item.definition}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {query.trim() && results.length === 0 && !loading && (
        <p className="px-1 text-xs text-muted-foreground">
          No results for &ldquo;{query}&rdquo;
        </p>
      )}
    </div>
  );
}
