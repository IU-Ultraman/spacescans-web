"use client";

import { useEffect, useMemo, useState } from "react";
import { ComposableMap, Geographies, Geography } from "react-simple-maps";
import * as topojson from "topojson-client";
import { api, type ResultsPreview, type StateGeoBucket } from "@/lib/api";
import { isInputColumn } from "@/lib/result-columns";
import { Map as MapIcon } from "lucide-react";

// Raw lng/lat states topojson. We let react-simple-maps' geoAlbersUsa
// projection do the composite US layout (incl. AK/HI insets) + auto-fit,
// rather than the pre-projected albers file (which double-translates under
// ComposableMap's centering and clips the map to the NW corner).
import statesGeo from "us-atlas/states-10m.json";

interface StateMapCardProps {
  taskId: string;
  preview: ResultsPreview | null;
}

type Metric = "count" | "mean";

interface StateBucketMap {
  [stateFips: string]: StateGeoBucket;
}

function interpolateColor(t: number): string {
  // 5-stop sequential gradient: light gray → emerald-200 → emerald-500 → emerald-700.
  // t ∈ [0, 1]. Returns an HSL string.
  if (!Number.isFinite(t)) return "hsl(220 14% 90%)";
  const clamped = Math.max(0, Math.min(1, t));
  // Hue stays ~emerald; lightness goes 90% (lightest) → 32% (darkest).
  const lightness = 90 - clamped * 58;
  const saturation = 30 + clamped * 50;
  return `hsl(160 ${saturation}% ${lightness}%)`;
}

export function StateMapCard({ taskId, preview }: StateMapCardProps) {
  // Pick the first numeric exposure column as default.
  const numericExposureCols = useMemo(() => {
    if (!preview) return [];
    return preview.summary
      .filter((c) => c.dtype === "numeric" && !isInputColumn(c.name))
      .map((c) => c.name);
  }, [preview]);

  const [valueCol, setValueCol] = useState<string>("");
  const [metric, setMetric] = useState<Metric>("count");
  const [data, setData] = useState<StateBucketMap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [hovered, setHovered] = useState<{ name: string; fips: string } | null>(
    null,
  );

  // Default value column once preview loads.
  useEffect(() => {
    if (numericExposureCols.length > 0 && !valueCol) {
      setValueCol(numericExposureCols[0]);
    }
  }, [numericExposureCols, valueCol]);

  // Fetch geo aggregation whenever value_col changes.
  useEffect(() => {
    if (!valueCol) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getResultsGeo(taskId, valueCol)
      .then((r) => {
        if (cancelled) return;
        const map: StateBucketMap = {};
        for (const b of r.by_state) {
          map[b.state_fips.padStart(2, "0")] = b;
        }
        setData(map);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load geo data");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [taskId, valueCol]);

  // Convert topojson states feature collection.
  // The `id` on each feature is the 2-digit state FIPS.
  const stateFeatures = useMemo(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const topo = statesGeo as any;
    const fc = topojson.feature(topo, topo.objects.states) as unknown as {
      features: Array<{
        id?: string | number;
        properties: { name: string };
      }>;
    };
    return fc.features;
  }, []);

  const range = useMemo(() => {
    if (!data) return { lo: 0, hi: 0 };
    const values: number[] = [];
    for (const b of Object.values(data)) {
      const v = metric === "count" ? b.count : b.mean;
      if (v !== null && Number.isFinite(v)) values.push(v);
    }
    if (values.length === 0) return { lo: 0, hi: 0 };
    return { lo: Math.min(...values), hi: Math.max(...values) };
  }, [data, metric]);

  if (numericExposureCols.length === 0) return null;

  function colorFor(fips: string): string {
    if (!data) return "hsl(220 14% 92%)";
    const b = data[fips.padStart(2, "0")];
    if (!b) return "hsl(220 14% 92%)";
    const v = metric === "count" ? b.count : b.mean;
    if (v === null || !Number.isFinite(v)) return "hsl(220 14% 92%)";
    const span = range.hi - range.lo;
    const t = span > 0 ? (v - range.lo) / span : 0.5;
    return interpolateColor(t);
  }

  const hoveredBucket = hovered ? data?.[hovered.fips.padStart(2, "0")] : null;

  return (
    <div className="rounded-lg border bg-card p-6 shadow-sm">
      <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <MapIcon className="size-4" />
        Geographic Distribution
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Per-state aggregation across the cohort. Hover a state for details.
      </p>

      {/* Toolbar */}
      <div className="mt-4 flex flex-wrap items-center gap-3 text-xs">
        <label className="flex items-center gap-2">
          <span className="text-muted-foreground">Value:</span>
          <select
            value={valueCol}
            onChange={(e) => setValueCol(e.target.value)}
            className="rounded-md border bg-background px-2 py-1 font-mono"
          >
            {numericExposureCols.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <div className="flex overflow-hidden rounded-md border">
          {(["count", "mean"] as Metric[]).map((m) => (
            <button
              key={m}
              onClick={() => setMetric(m)}
              className={
                "px-2 py-1 transition-colors " +
                (metric === m
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:bg-muted")
              }
            >
              {m}
            </button>
          ))}
        </div>
        {loading && (
          <span className="text-[10px] text-muted-foreground">Loading…</span>
        )}
        {error && (
          <span className="text-[10px] text-destructive">{error}</span>
        )}
      </div>

      {/* Map + legend */}
      <div className="relative mt-4">
        <ComposableMap
          projection="geoAlbersUsa"
          projectionConfig={{ scale: 1070 }}
          width={975}
          height={610}
          style={{ width: "100%", height: "auto" }}
        >
          <Geographies geography={stateFeatures}>
            {({ geographies }) =>
              geographies.map((geo) => {
                const fips = String(geo.id ?? "");
                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={colorFor(fips)}
                    stroke="#fff"
                    strokeWidth={0.5}
                    onMouseEnter={() =>
                      setHovered({
                        name: geo.properties.name as string,
                        fips,
                      })
                    }
                    onMouseLeave={() => setHovered(null)}
                    style={{
                      default: { outline: "none" },
                      hover: { outline: "none", fill: "hsl(160 70% 35%)" },
                      pressed: { outline: "none" },
                    }}
                  />
                );
              })
            }
          </Geographies>
        </ComposableMap>

        {/* Hover tooltip */}
        {hovered && (
          <div className="pointer-events-none absolute right-3 top-3 rounded-md border bg-popover px-2.5 py-1.5 text-xs shadow">
            <div className="font-medium">{hovered.name}</div>
            <div className="font-mono text-[10px] text-muted-foreground">
              FIPS {hovered.fips}
            </div>
            {hoveredBucket ? (
              <>
                <div className="font-mono text-[10px]">
                  count: {hoveredBucket.count.toLocaleString()}
                </div>
                <div className="font-mono text-[10px]">
                  mean:{" "}
                  {hoveredBucket.mean === null
                    ? "—"
                    : hoveredBucket.mean.toFixed(4)}
                </div>
              </>
            ) : (
              <div className="text-[10px] text-muted-foreground italic">no data</div>
            )}
          </div>
        )}
      </div>

      {/* Legend */}
      {data && Object.keys(data).length > 0 && (
        <div className="mt-3 flex items-center gap-2 text-[10px] text-muted-foreground">
          <span className="font-mono tabular-nums">
            {metric === "count"
              ? range.lo.toLocaleString()
              : range.lo.toFixed(2)}
          </span>
          <div className="h-2 flex-1 rounded-full bg-gradient-to-r from-[hsl(160_30%_90%)] via-[hsl(160_55%_60%)] to-[hsl(160_80%_32%)]" />
          <span className="font-mono tabular-nums">
            {metric === "count"
              ? range.hi.toLocaleString()
              : range.hi.toFixed(2)}
          </span>
        </div>
      )}
    </div>
  );
}
