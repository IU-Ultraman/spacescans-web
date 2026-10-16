"use client";

import { Download } from "lucide-react";
import type { DatasetKind, DatasetTemporal } from "@/lib/datasets";

// A realistic sample per geography: the right key width (zero-padded codes
// from Leon County, FL) and a column name the first guess recognises.
const SAMPLE_KEY: Record<string, { col: string; codes: [string, string] }> = {
  Tract: { col: "tract", codes: ["12073000200", "12073000301"] },
  BG: { col: "bg_geoid", codes: ["120730002001", "120730002002"] },
  ZCTA5: { col: "zcta", codes: ["32301", "32303"] },
  County: { col: "county_fips", codes: ["12073", "12065"] },
};

export function csvExample(geography: string, temporal: DatasetTemporal): string {
  const k = SAMPLE_KEY[geography] ?? SAMPLE_KEY.Tract;
  if (temporal === "yearly") {
    return [
      `${k.col},year,ndvi`,
      `${k.codes[0]},2013,0.300`,
      `${k.codes[0]},2014,0.350`,
      `${k.codes[1]},2013,0.301`,
      `${k.codes[1]},2014,0.351`,
    ].join("\n");
  }
  if (temporal === "daily") {
    return [
      `${k.col},date,tmax_c`,
      `${k.codes[0]},2014-01-01,18.2`,
      `${k.codes[0]},2014-01-02,19.0`,
      `${k.codes[1]},2014-01-01,18.4`,
      `${k.codes[1]},2014-01-02,19.3`,
    ].join("\n");
  }
  return [
    `${k.col},greenness,heat_index`,
    `${k.codes[0]},0.345,82.8`,
    `${k.codes[1]},0.346,82.9`,
  ].join("\n");
}

function downloadText(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

const RASTER_NAMES: Record<DatasetTemporal, string> = {
  static: "greenness.tif",
  yearly: "ndvi_2013.tif\nndvi_2014.tif\n…  (one file per year, selected together)",
  biweekly:
    "no2_2014001-2014014.tif   (start-end as year + day of year)\nno2_2014-01-15.tif        (start only: a 14-day period)\n…  (one file per period, selected together)",
  daily: "tmax_2014-01-01.tif\ntmax_20140102.tif\n…  (one file per day, selected together)",
};

/** What an upload must look like, given the kind and time structure chosen. */
export function DatasetFormatGuide({
  kind,
  temporal,
  geography,
  keyLen,
}: {
  kind: DatasetKind;
  temporal: DatasetTemporal;
  geography: string;
  keyLen: number | null;
}) {
  if (kind === "polygon_table") {
    const text = csvExample(geography, temporal);
    const rows = text.split("\n").map((line) => line.split(","));
    return (
      <div className="rounded-md border bg-muted/30 p-3 text-xs">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="font-medium">Example format</span>
          <button
            type="button"
            onClick={() => downloadText(`example_${geography.toLowerCase()}_${temporal}.csv`, text + "\n")}
            className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
          >
            <Download className="size-3" /> Download example CSV
          </button>
        </div>
        <div className="overflow-x-auto rounded border bg-background">
          <table className="w-full font-mono text-[11px]">
            <thead>
              <tr className="border-b bg-muted/40">
                {rows[0].map((h) => (
                  <th key={h} className="px-2 py-1 text-left font-semibold">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(1).map((r, i) => (
                <tr key={i} className="border-b last:border-0">
                  {r.map((cell, j) => (
                    <td key={j} className="px-2 py-1 tabular-nums">{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ul className="mt-2 list-disc space-y-0.5 pl-4 text-muted-foreground">
          <li>
            A CSV with a header row, then one row per area
            {temporal === "yearly" ? " and year" : temporal === "daily" ? " and day" : ""}.
          </li>
          <li>
            One column holds the area code
            {keyLen ? `: ${keyLen} digits, zero-padded (spreadsheets drop leading zeros; keep the column as text)` : ""}.
            Name it anything; you pick it below.
          </li>
          {temporal === "yearly" && <li>One column holds a four-digit year.</li>}
          {temporal === "daily" && <li>One column holds the date, written YYYY-MM-DD.</li>}
          <li>Every other column you select becomes a result column; values must be numeric. Blank, NA or N/A means missing.</li>
        </ul>
      </div>
    );
  }

  if (kind === "raster") {
    return (
      <div className="rounded-md border bg-muted/30 p-3 text-xs">
        <div className="mb-2 font-medium">Example format</div>
        <pre className="overflow-x-auto rounded bg-background p-2 font-mono text-[11px] leading-5">
          {RASTER_NAMES[temporal]}
        </pre>
        <ul className="mt-2 list-disc space-y-0.5 pl-4 text-muted-foreground">
          <li>GeoTIFF (.tif) with a coordinate reference system, north-up (the default export of QGIS, ArcGIS, R terra or Python rasterio).</li>
          <li>Covers the part of the contiguous US where your cohort lives.</li>
          <li>Each band you list becomes its own result column; set a nodata value for cells without data.</li>
          {temporal !== "static" && <li>Every file on the same grid: same size, resolution and CRS.</li>}
          {temporal === "yearly" && <li>The year is read from each file name; you can correct it.</li>}
          {temporal === "biweekly" && (
            <li>
              Each file covers one two-week period. Its start (and end, if present) is read from the
              name — 2014-01-01, 20140101, or 2014001 as year plus day of year — and you can correct
              both; without an end, the period is the 14 days from the start.
            </li>
          )}
          {temporal === "daily" && <li>Each file covers one day, read from its name (2014-01-01, 20140101 or 2014001); you can correct it.</li>}
        </ul>
      </div>
    );
  }

  return (
    <div className="rounded-md border bg-muted/30 p-3 text-xs">
      <div className="mb-2 font-medium">Example format</div>
      <pre className="overflow-x-auto rounded bg-background p-2 font-mono text-[11px] leading-5">
        {temporal === "yearly"
          ? "parks_2014.gpkg\nparks_2015.gpkg\n…  (one file per year)  — or one file with a year attribute"
          : "parks.gpkg   or   parks.geojson   or   parks.zip (a zipped shapefile)"}
      </pre>
      <ul className="mt-2 list-disc space-y-0.5 pl-4 text-muted-foreground">
        <li>GeoPackage (.gpkg), GeoJSON (.geojson), or a shapefile zipped with its .shp, .shx, .dbf and .prj.</li>
        <li>One geometry type per dataset: points, lines or polygons.</li>
        <li>A coordinate reference system is required; the features must lie in the contiguous US.</li>
        <li>The result is the straight-line distance in metres from each location to the nearest feature; no buffer is used.</li>
      </ul>
    </div>
  );
}
