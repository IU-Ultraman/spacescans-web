"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { LogEntry } from "@/lib/api";

// Re-export so existing `import { LogEntry } from "@/components/log-viewer"`
// usages keep compiling. The canonical definition lives in `@/lib/api`.
export type { LogEntry };

interface LogViewerProps {
  logs: LogEntry[];
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
}

function levelColor(level: string): string {
  switch (level.toLowerCase()) {
    case "info":
      return "text-emerald-400";
    case "warn":
    case "warning":
      return "text-yellow-400";
    case "error":
      return "text-red-400";
    default:
      return "text-slate-400";
  }
}

function sourceBadgeClass(source: string): string {
  switch (source) {
    case "runner":
      return "bg-slate-700 text-slate-300";
    case "c3_bg":
      return "bg-blue-500/15 text-blue-300";
    case "c4_ndi":
      return "bg-emerald-500/15 text-emerald-300";
    case "c4_wi":
      return "bg-violet-500/15 text-violet-300";
    default:
      return "bg-slate-700 text-slate-400";
  }
}

export function LogViewer({ logs }: LogViewerProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Discover which sources appear in the log stream so we only render
  // filter chips for sources that are actually present.
  const availableSources = useMemo(() => {
    const seen = new Set<string>();
    for (const entry of logs) {
      if (entry.source) seen.add(entry.source);
    }
    return Array.from(seen);
  }, [logs]);

  // Set of *enabled* sources (i.e. shown). Empty set means "no filter
  // configured yet" — we treat that as "show everything" so newly
  // appearing sources don't get silently hidden.
  const [enabledSources, setEnabledSources] = useState<Set<string>>(new Set());

  const visibleLogs = useMemo(() => {
    if (enabledSources.size === 0) return logs;
    return logs.filter((entry) => {
      // Entries without a source (legacy / non-pipeline lines) are always shown.
      if (!entry.source) return true;
      return enabledSources.has(entry.source);
    });
  }, [logs, enabledSources]);

  function toggleSource(source: string) {
    setEnabledSources((prev) => {
      const next = new Set(prev);
      // First click: switch from "show all" to a single-source filter.
      if (next.size === 0) {
        for (const s of availableSources) {
          if (s !== source) next.add(s);
        }
        return next;
      }
      if (next.has(source)) {
        next.delete(source);
        // If user disabled the last enabled source, fall back to "show all".
        if (next.size === 0) return new Set();
      } else {
        next.add(source);
        // If user re-enabled every source, collapse back to "show all".
        if (next.size === availableSources.length) return new Set();
      }
      return next;
    });
  }

  function isSourceActive(source: string): boolean {
    return enabledSources.size === 0 || enabledSources.has(source);
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visibleLogs.length]);

  return (
    <div className="overflow-hidden rounded-lg border border-slate-700 bg-slate-900 shadow-inner">
      {/* Terminal header bar */}
      <div className="flex items-center gap-2 border-b border-slate-700 bg-slate-800 px-4 py-2">
        <span className="size-3 rounded-full bg-red-500/80" />
        <span className="size-3 rounded-full bg-yellow-500/80" />
        <span className="size-3 rounded-full bg-green-500/80" />
        <span className="ml-3 text-xs font-medium text-slate-400">
          Task Logs
        </span>
        {availableSources.length > 1 && (
          <div className="ml-auto flex items-center gap-1">
            {availableSources.map((source) => {
              const active = isSourceActive(source);
              return (
                <button
                  key={source}
                  type="button"
                  onClick={() => toggleSource(source)}
                  className={cn(
                    "rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide transition-opacity",
                    sourceBadgeClass(source),
                    active ? "opacity-100" : "opacity-40",
                  )}
                  title={
                    active
                      ? `Hide ${source} logs`
                      : `Show ${source} logs`
                  }
                >
                  {source}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Log content */}
      <div
        ref={containerRef}
        className="h-[400px] overflow-y-auto p-4 font-mono text-sm leading-relaxed"
      >
        {visibleLogs.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <span className="text-slate-500">
              {logs.length === 0
                ? "Waiting for log output..."
                : "No log lines match the current source filter."}
            </span>
          </div>
        ) : (
          visibleLogs.map((entry, i) => (
            <div
              key={i}
              className="flex gap-2 py-0.5 hover:bg-slate-800/50"
            >
              <span className="shrink-0 text-slate-500">
                [{formatTime(entry.ts)}]
              </span>
              {entry.source && (
                <span
                  className={cn(
                    "shrink-0 rounded px-1 text-[10px] font-medium uppercase leading-5 tracking-wide",
                    sourceBadgeClass(entry.source),
                  )}
                >
                  {entry.source}
                </span>
              )}
              <span
                className={`shrink-0 font-semibold uppercase ${levelColor(entry.level)}`}
              >
                {entry.level.toUpperCase().padEnd(5)}
              </span>
              <span className="text-slate-200">{entry.msg}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
