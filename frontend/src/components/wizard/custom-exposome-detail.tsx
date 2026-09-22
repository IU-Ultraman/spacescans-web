"use client";

import type { CustomExposome } from "@/lib/api";
import { BOUNDARY_LABEL, type BoundaryKey } from "@/lib/variable-grouping";

/**
 * The right-hand panel for a custom exposome — the counterpart to
 * OntologyNodeDetail, which cannot describe these: they have no ontology node.
 * Deliberately echoes that panel's field rows so the two read as one surface.
 */
export function CustomExposomeDetail({ dataset }: { dataset: CustomExposome }) {
  const isRaster = dataset.geometry === "raster";
  const files = dataset.rasters?.map((r) => r.uploaded_filename).join(", ");
  const rows: [string, string][] = [
    ["Data Source", `Uploaded — ${isRaster ? files : dataset.uploaded_filename}`],
    [
      "Spatial Scale",
      isRaster && dataset.grid
        ? `${dataset.grid.resolution_label} grid (${dataset.grid.width.toLocaleString()} × ${dataset.grid.height.toLocaleString()} cells, ${dataset.grid.crs})`
        : BOUNDARY_LABEL[dataset.boundary as BoundaryKey] ?? dataset.boundary,
    ],
    [
      "Linked as",
      isRaster
        ? "Cell-coverage-weighted within the residential buffer"
        : `Area-weighted from ${dataset.boundary}`,
    ],
    [
      "Temporal",
      dataset.temporal === "yearly"
        ? `Time-varying (${dataset.year_col})`
        : "Time-invariant",
    ],
    [
      "Years Available",
      dataset.temporal === "yearly"
        ? `${dataset.coverage_years[0]}–${dataset.coverage_years[1]}`
        : "Any study period",
    ],
    isRaster
      ? ["Band", String(dataset.band ?? 1)]
      : [
          "Rows",
          `${dataset.row_count.toLocaleString()} (${dataset.distinct_keys.toLocaleString()} distinct ${dataset.boundary} codes)`,
        ],
    isRaster
      ? [
          "Extent",
          dataset.grid
            ? `lon ${dataset.grid.bounds_wgs84[0].toFixed(1)}…${dataset.grid.bounds_wgs84[2].toFixed(1)}, lat ${dataset.grid.bounds_wgs84[1].toFixed(1)}…${dataset.grid.bounds_wgs84[3].toFixed(1)}`
            : "—",
        ]
      : ["Joins on", `${dataset.key_col} → ${dataset.join_col}`],
  ];

  return (
    <div className="rounded-lg border p-5">
      <h2 className="text-xl font-semibold">{dataset.label}</h2>

      <dl className="mt-4 space-y-2">
        {rows.map(([term, value]) => (
          <div key={term} className="grid grid-cols-[9rem_1fr] gap-2 text-sm">
            <dt className="text-muted-foreground">{term}</dt>
            <dd className="min-w-0 break-words">{value}</dd>
          </div>
        ))}
      </dl>

      {dataset.description && (
        <>
          <h3 className="mt-5 text-xs uppercase tracking-wide text-muted-foreground">
            Description
          </h3>
          <p className="mt-1 text-sm">{dataset.description}</p>
        </>
      )}

      <h3 className="mt-5 text-xs uppercase tracking-wide text-muted-foreground">
        Exposomes ({dataset.value_cols.length})
      </h3>
      <div className="mt-2 space-y-2">
        {dataset.value_cols.map((col) => (
          <div key={col} className="rounded-md border px-3 py-2">
            <div className="flex items-baseline gap-2">
              <span className="text-sm font-medium">
                {dataset.value_labels?.[col] ?? col}
              </span>
              <code className="text-xs text-muted-foreground">{col}</code>
              {dataset.value_units?.[col] && (
                <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                  {dataset.value_units[col]}
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {isRaster
                ? "Coverage-weighted mean of the raster cells under the residential buffer"
                : "Area-weighted over the residential buffer"}
              {dataset.temporal === "yearly"
                ? ", averaged across each episode's years."
                : "."}{" "}
              (Result column: {col}.)
            </p>
          </div>
        ))}
      </div>

      <p className="mt-5 text-xs text-muted-foreground">
        Uploaded {new Date(dataset.created_at).toLocaleDateString()}. Visible
        only to you.
      </p>
    </div>
  );
}
