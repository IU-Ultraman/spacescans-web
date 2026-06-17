"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type HistogramData } from "@/lib/api";
import { BarChart3 } from "lucide-react";

interface HistogramsCardProps {
  taskId: string;
}

function formatBinLabel(edge: number): string {
  if (Number.isInteger(edge)) return edge.toLocaleString();
  if (Math.abs(edge) < 0.01 || Math.abs(edge) >= 1e5) {
    return edge.toExponential(1);
  }
  return edge.toFixed(2);
}

interface BinPoint {
  range: string;
  count: number;
}

function toChartData(hist: HistogramData): BinPoint[] {
  // bins has length counts.length + 1 (np.histogram edge convention).
  // Each bar represents [edges[i], edges[i+1]).
  const points: BinPoint[] = [];
  for (let i = 0; i < hist.counts.length; i++) {
    const lo = hist.bins[i];
    const hi = hist.bins[i + 1];
    points.push({
      range: `${formatBinLabel(lo)}–${formatBinLabel(hi)}`,
      count: hist.counts[i],
    });
  }
  return points;
}

function HistogramTile({ hist }: { hist: HistogramData }) {
  const data = toChartData(hist);
  return (
    <div className="rounded-md border p-3">
      <div className="flex items-baseline justify-between">
        <span className="font-mono text-xs font-medium">{hist.name}</span>
        <span className="text-[10px] text-muted-foreground tabular-nums">
          n={hist.sample_size.toLocaleString()}
        </span>
      </div>
      <div className="mt-2 h-32">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ top: 4, right: 4, bottom: 4, left: 4 }}
          >
            <XAxis dataKey="range" hide />
            <YAxis hide />
            <Tooltip
              cursor={{ fill: "rgba(0,0,0,0.04)" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const p = payload[0].payload as BinPoint;
                return (
                  <div className="rounded-md border bg-popover px-2 py-1 text-[10px] shadow">
                    <div className="font-mono">{p.range}</div>
                    <div className="font-mono">count: {p.count.toLocaleString()}</div>
                  </div>
                );
              }}
            />
            <Bar dataKey="count" fill="hsl(217 91% 60%)" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex justify-between text-[10px] font-mono text-muted-foreground tabular-nums">
        <span>{hist.min !== null ? formatBinLabel(hist.min) : "—"}</span>
        <span>{hist.max !== null ? formatBinLabel(hist.max) : "—"}</span>
      </div>
    </div>
  );
}

export function HistogramsCard({ taskId }: HistogramsCardProps) {
  const [data, setData] = useState<HistogramData[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getResultsHistogram(taskId, 20)
      .then((r) => {
        if (!cancelled) setData(r.histograms);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load histograms");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [taskId]);

  if (error) {
    return (
      <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-4 text-sm text-amber-700 dark:text-amber-400">
        Histograms unavailable: {error}
      </div>
    );
  }
  if (!data) {
    return (
      <div className="rounded-lg border bg-card p-6 shadow-sm">
        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <BarChart3 className="size-4" />
          Exposure Histograms
        </div>
        <p className="mt-2 text-xs text-muted-foreground">Loading…</p>
      </div>
    );
  }
  if (data.length === 0) {
    return null; // no numeric exposures → don't render the card
  }

  return (
    <div className="rounded-lg border bg-card p-6 shadow-sm">
      <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <BarChart3 className="size-4" />
        Exposure Histograms
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        20-bin distributions across all rows. Hover for bin counts.
      </p>
      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        {data.map((hist) => (
          <HistogramTile key={hist.name} hist={hist} />
        ))}
      </div>
    </div>
  );
}
