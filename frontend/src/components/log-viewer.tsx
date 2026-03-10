"use client";

import { useEffect, useRef } from "react";

export interface LogEntry {
  ts: string;
  level: string;
  msg: string;
}

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

export function LogViewer({ logs }: LogViewerProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

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
      </div>

      {/* Log content */}
      <div
        ref={containerRef}
        className="h-[400px] overflow-y-auto p-4 font-mono text-sm leading-relaxed"
      >
        {logs.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <span className="text-slate-500">Waiting for log output...</span>
          </div>
        ) : (
          logs.map((entry, i) => (
            <div
              key={i}
              className="flex gap-2 py-0.5 hover:bg-slate-800/50"
            >
              <span className="shrink-0 text-slate-500">
                [{formatTime(entry.ts)}]
              </span>
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
