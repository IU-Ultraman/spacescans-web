"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Download, FileUp, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  api, ApiError,
  type CustomBoundary, type CustomExposome, type CustomPreview, type CustomRasterPreview,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const NO_YEAR = "__none__";
const COLUMN_NAME = /^[A-Za-z][A-Za-z0-9_]*$/;

type Kind = "table" | "raster";
type Temporal = "static" | "yearly";

interface RasterPick {
  file: File;
  meta: CustomRasterPreview | null;
  error: string | null;
  /** Text so the field can be blank; parsed on save. */
  year: string;
}

/** Only the entries for columns that are actually selected, trimmed, non-empty. */
function pick(map: Record<string, string>, keys: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of keys) {
    const v = (map[k] ?? "").trim();
    if (v) out[k] = v;
  }
  return out;
}

// A realistic sample per boundary: the right key width (a zero-padded code from
// Leon County, FL) and a column name the auto-detect recognises.
const SAMPLE_KEY: Record<string, { col: string; codes: [string, string, string] }> = {
  Tract: { col: "tract", codes: ["12073000200", "12073000301", "12073000302"] },
  BG: { col: "bg_geoid", codes: ["120730002001", "120730002002", "120730003011"] },
  ZCTA5: { col: "zcta", codes: ["32301", "32303", "32304"] },
  County: { col: "county_fips", codes: ["12073", "12065", "12039"] },
};

function csvExample(boundary: string, temporal: Temporal): string {
  const k = SAMPLE_KEY[boundary] ?? SAMPLE_KEY.Tract;
  if (temporal === "static") {
    return [
      `${k.col},greenness,heat_index`,
      `${k.codes[0]},0.345,82.8`,
      `${k.codes[1]},0.346,82.9`,
      `${k.codes[2]},0.351,83.4`,
    ].join("\n");
  }
  return [
    `${k.col},year,ndvi`,
    `${k.codes[0]},2013,0.300`,
    `${k.codes[0]},2014,0.350`,
    `${k.codes[1]},2013,0.301`,
    `${k.codes[1]},2014,0.351`,
  ].join("\n");
}

function downloadText(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

/** What the upload must look like, given the two choices already made. */
function ExampleFormat({
  kind, temporal, boundary, keyLen,
}: { kind: Kind; temporal: Temporal; boundary: string; keyLen: number | null }) {
  if (kind === "table") {
    const text = csvExample(boundary, temporal);
    const rows = text.split("\n").map((line) => line.split(","));
    return (
      <div className="rounded-md border bg-muted/30 p-3 text-xs">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="font-medium">Example format</span>
          <button
            type="button"
            onClick={() =>
              downloadText(`example_${boundary.toLowerCase()}_${temporal}.csv`, text + "\n")
            }
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
            Saved as CSV: a header row, then{" "}
            {temporal === "static" ? "one row per polygon" : "one row per polygon per year"},
            cells separated by commas.
          </li>
          <li>
            One column holds the {boundary} code
            {keyLen ? ` — ${keyLen} digits, zero-padded (Excel drops the leading 0; save as text)` : ""}.
            Name it anything; you pick it in the next step.
          </li>
          {temporal === "yearly" && <li>One column holds a four-digit year.</li>}
          <li>
            Every other column you select becomes an exposure; values must be
            numeric. Blank, NA or N/A means missing.
          </li>
        </ul>
      </div>
    );
  }
  return (
    <div className="rounded-md border bg-muted/30 p-3 text-xs">
      <div className="mb-2 font-medium">Example format</div>
      <pre className="overflow-x-auto rounded bg-background p-2 font-mono text-[11px] leading-5">
        {temporal === "static"
          ? "greenness.tif"
          : "ndvi_2013.tif\nndvi_2014.tif\nndvi_2015.tif\n…  (one file per year, selected together)"}
      </pre>
      <ul className="mt-2 list-disc space-y-0.5 pl-4 text-muted-foreground">
        <li>GeoTIFF (.tif) with a coordinate reference system — any CRS, any resolution.</li>
        <li>North-up (the default export from QGIS, ArcGIS, R terra or Python rasterio).</li>
        <li>Covers the part of the continental US your cohort lives in.</li>
        <li>
          One numeric band is used (you can choose which); set a nodata value for
          cells without data.
        </li>
        {temporal === "yearly" && (
          <li>Every year on the same grid — same size, resolution and CRS. A year in the filename is picked up automatically.</li>
        )}
      </ul>
    </div>
  );
}

interface CustomExposomeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (dataset: CustomExposome) => void | Promise<void>;
}

/**
 * Upload a table or a raster, say what its parts mean, save.
 *
 * The mapping is a form rather than guesswork: a wrong guess produces a dataset
 * that links nothing, and the server can only check the *shape* of a
 * geography key, never its membership in the real key universe.
 */
export function CustomExposomeDialog({
  open, onOpenChange, onCreated,
}: CustomExposomeDialogProps) {
  const [kind, setKind] = useState<Kind>("table");
  // Asked explicitly rather than inferred from "is there a year column" or
  // "how many files": the user should say whether the values vary by year,
  // and the rest of the form then asks only for what that needs.
  const [temporal, setTemporal] = useState<Temporal>("static");

  // --- table (CSV on a Census geography) ---
  const [boundaries, setBoundaries] = useState<CustomBoundary[] | null>(null);
  const [boundary, setBoundary] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<CustomPreview | null>(null);
  const [keyCol, setKeyCol] = useState("");
  const [yearCol, setYearCol] = useState<string>(NO_YEAR);
  const [valueCols, setValueCols] = useState<string[]>([]);
  // Per value column. One dataset can carry a greenness index next to a
  // temperature, so a single dataset-level unit cannot be right.
  const [colLabels, setColLabels] = useState<Record<string, string>>({});
  const [colUnits, setColUnits] = useState<Record<string, string>>({});

  // --- raster (one GeoTIFF, or one per year) ---
  const [rasters, setRasters] = useState<RasterPick[]>([]);
  const [band, setBand] = useState(1);
  const [rasterCol, setRasterCol] = useState("value");
  const [rasterLabel, setRasterLabel] = useState("");
  const [rasterUnit, setRasterUnit] = useState("");

  // --- shared ---
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState<"preview" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    api
      .listCustomBoundaries()
      .then((res) => {
        setBoundaries(res.boundaries);
        const firstAvailable = res.boundaries.find((b) => b.available);
        setBoundary((current) => current || firstAvailable?.boundary || "");
      })
      .catch(() => setBoundaries([]));
  }, [open]);

  const reset = () => {
    setKind("table"); setTemporal("static");
    setFile(null); setPreview(null); setKeyCol(""); setYearCol(NO_YEAR);
    setValueCols([]); setColLabels({}); setColUnits({});
    setRasters([]); setBand(1); setRasterCol("value"); setRasterLabel(""); setRasterUnit("");
    setName(""); setDescription("");
    setError(null); setBusy(null);
  };

  const chooseTemporal = (next: Temporal) => {
    setTemporal(next);
    setError(null);
    if (next === "static") setYearCol(NO_YEAR);
    setRasters([]);              // file count and per-file years depend on it
  };

  const close = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  // ---------------------------------------------------------------- table ---

  const pickFile = async (picked: File | null) => {
    setFile(picked);
    setPreview(null);
    setKeyCol(""); setYearCol(NO_YEAR); setValueCols([]);
    setError(null);
    if (!picked) return;
    setBusy("preview");
    try {
      const result = await api.previewCustomExposome(picked);
      setPreview(result);
      if (!name) setName(picked.name.replace(/\.(csv|txt)$/i, ""));
      // Sensible first guesses the user can correct: a column whose name looks
      // like a geography key, and a "year" column if one is present.
      const geo = result.columns.find((c) =>
        /^(geoid|fips|tract|bg|zcta|zip|county|geo)/i.test(c.name),
      );
      if (geo) setKeyCol(geo.name);
      const year = result.columns.find((c) => /^year$/i.test(c.name));
      if (year && temporal === "yearly") setYearCol(year.name);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not read that file");
    } finally {
      setBusy(null);
    }
  };

  const available = useMemo(
    () => (boundaries ?? []).filter((b) => b.available),
    [boundaries],
  );
  const activeBoundary = available.find((b) => b.boundary === boundary);

  const toggleValueCol = (column: string, checked: boolean) => {
    setValueCols((prev) =>
      checked ? [...prev, column] : prev.filter((c) => c !== column),
    );
  };

  const reserved = new Set([keyCol, yearCol === NO_YEAR ? "" : yearCol]);

  // --------------------------------------------------------------- raster ---

  const pickRasters = async (list: FileList | null) => {
    const files = list ? Array.from(list) : [];
    setError(null);
    const picks: RasterPick[] = files.map((f) => ({
      file: f, meta: null, error: null,
      // A four-digit year in the filename is a reasonable first guess.
      year: temporal === "yearly" ? (f.name.match(/(?:19|20)\d{2}/) ?? [""])[0] : "",
    }));
    setRasters(picks);
    if (!files.length) return;
    if (!name) {
      setName(files[0].name.replace(/\.(tif|tiff)$/i, "").replace(/[_-]?(?:19|20)\d{2}/, ""));
    }
    setBusy("preview");
    for (let i = 0; i < picks.length; i++) {
      try {
        const meta = await api.previewCustomRaster(picks[i].file);
        setRasters((prev) => prev.map((p, j) => (j === i ? { ...p, meta } : p)));
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : "Could not read that file";
        setRasters((prev) => prev.map((p, j) => (j === i ? { ...p, error: msg } : p)));
      }
    }
    setBusy(null);
  };

  const firstMeta = rasters.find((r) => r.meta)?.meta ?? null;
  const gridMismatch = useMemo(() => {
    const hashes = new Set(rasters.filter((r) => r.meta).map((r) => r.meta!.grid_hash));
    return hashes.size > 1;
  }, [rasters]);
  const rastersReady =
    rasters.length > 0 && rasters.every((r) => r.meta && !r.error) && !gridMismatch;
  const yearsOk =
    temporal === "static"
      ? rasters.length === 1
      : rasters.length > 0 &&
        rasters.every((r) => /^\d{4}$/.test(r.year.trim())) &&
        new Set(rasters.map((r) => r.year.trim())).size === rasters.length;

  // ----------------------------------------------------------------- save ---

  const canSave =
    busy === null &&
    name.trim().length > 0 &&
    (kind === "table"
      ? !!file && !!preview && !!boundary && !!keyCol && valueCols.length > 0 &&
        (temporal === "static" || yearCol !== NO_YEAR)
      : rastersReady && yearsOk && COLUMN_NAME.test(rasterCol.trim()));

  const save = async () => {
    setBusy("save");
    setError(null);
    try {
      let created: CustomExposome;
      if (kind === "table") {
        if (!file) return;
        created = await api.createCustomExposome({
          file,
          name: name.trim(),
          boundary,
          key_col: keyCol,
          value_cols: valueCols,
          description,
          value_labels: pick(colLabels, valueCols),
          value_units: pick(colUnits, valueCols),
          year_col: temporal === "yearly" && yearCol !== NO_YEAR ? yearCol : null,
        });
      } else {
        created = await api.createCustomRaster({
          files: rasters.map((r) => ({
            file: r.file,
            year: temporal === "yearly" ? Number(r.year.trim()) : null,
          })),
          name: name.trim(),
          value_col: rasterCol.trim(),
          band,
          description,
          value_label: rasterLabel,
          value_unit: rasterUnit,
        });
      }
      await onCreated(created);
      close(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the dataset");
    } finally {
      setBusy(null);
    }
  };

  const showNaming = kind === "table" ? !!preview : rasters.length > 0;

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add a custom exposome</DialogTitle>
          <DialogDescription>
            Upload your own values and they become selectable for any of your
            tasks — values per polygon (tract, block group, ZIP area or county)
            as a CSV, or a raster.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          {/* 1. kind (+ boundary for a table) */}
          <section className="space-y-2">
            <Label>1. What are you uploading?</Label>
            <div className="flex flex-wrap gap-2">
              {([
                ["table", "Polygon (CSV)"],
                ["raster", "Raster (GeoTIFF)"],
              ] as [Kind, string][]).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => { setKind(k); setError(null); }}
                  className={cn(
                    "rounded-md border px-3 py-1.5 text-xs transition-colors",
                    kind === k
                      ? "border-primary bg-primary/10 text-foreground"
                      : "text-muted-foreground hover:bg-muted/60",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>

            {kind === "table" && (
              <div className="space-y-2 pt-1">
                <span className="text-xs text-muted-foreground">
                  Which polygons do the rows describe?
                </span>
                {boundaries === null ? (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className="size-3.5 animate-spin" /> Checking what this
                    deployment provides…
                  </div>
                ) : available.length === 0 ? (
                  <p className="text-xs text-destructive">
                    This deployment has no boundary data provisioned, so polygon
                    values could not be computed. Add a boundary dataset on the Data Setup
                    page first — or upload a raster instead.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {available.map((b) => (
                      <button
                        key={b.boundary}
                        type="button"
                        onClick={() => setBoundary(b.boundary)}
                        className={cn(
                          "rounded-md border px-3 py-1.5 text-xs transition-colors",
                          boundary === b.boundary
                            ? "border-primary bg-primary/10 text-foreground"
                            : "text-muted-foreground hover:bg-muted/60",
                        )}
                      >
                        {b.label}
                      </button>
                    ))}
                  </div>
                )}
                {activeBoundary && (
                  <p className="text-xs text-muted-foreground">
                    Keys must be {activeBoundary.key_len}-digit codes, zero-padded
                    (the column joins to {activeBoundary.join_col}).
                  </p>
                )}
              </div>
            )}
          </section>

          {/* 2. static or yearly */}
          <section className="space-y-2">
            <Label>2. Do the values change over time?</Label>
            <div className="flex flex-wrap gap-2">
              {([
                ["static", "Time-invariant", "one value per area"],
                ["yearly", "Varies by year", "one value per area per year"],
              ] as [Temporal, string, string][]).map(([t, label, hint]) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => chooseTemporal(t)}
                  className={cn(
                    "rounded-md border px-3 py-1.5 text-left text-xs transition-colors",
                    temporal === t
                      ? "border-primary bg-primary/10 text-foreground"
                      : "text-muted-foreground hover:bg-muted/60",
                  )}
                >
                  <span className="font-medium">{label}</span>
                  <span className="ml-1.5 opacity-70">— {hint}</span>
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {temporal === "static"
                ? "The same value is used for every episode, whatever its dates."
                : "Each episode is matched to the years it spans and averaged by the days in each."}
            </p>
          </section>

          <ExampleFormat
            kind={kind}
            temporal={temporal}
            boundary={boundary || "Tract"}
            keyLen={activeBoundary?.key_len ?? null}
          />

          {/* 3. file(s) */}
          {kind === "table" ? (
            <section className="space-y-2">
              <Label htmlFor="custom-file">3. Your CSV</Label>
              <div className="flex items-center gap-3">
                <Input
                  id="custom-file"
                  type="file"
                  accept=".csv,.txt"
                  onChange={(e) => void pickFile(e.target.files?.[0] ?? null)}
                  className="cursor-pointer"
                />
                {busy === "preview" && (
                  <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />
                )}
              </div>
              {preview && (
                <p className="text-xs text-muted-foreground">
                  <FileUp className="mr-1 inline size-3" />
                  {preview.row_count.toLocaleString()} rows,{" "}
                  {preview.columns.length} columns
                </p>
              )}
            </section>
          ) : (
            <section className="space-y-2">
              <Label htmlFor="custom-rasters">
                3. {temporal === "static" ? "Your GeoTIFF" : "Your GeoTIFFs, one per year"}
              </Label>
              <div className="flex items-center gap-3">
                <Input
                  id="custom-rasters"
                  key={temporal}                 /* remount so a stale selection clears */
                  type="file"
                  accept=".tif,.tiff"
                  multiple={temporal === "yearly"}
                  onChange={(e) => void pickRasters(e.target.files)}
                  className="cursor-pointer"
                />
                {busy === "preview" && (
                  <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {temporal === "static"
                  ? "One north-up GeoTIFF with a CRS, over the continental US."
                  : "Select all the years at once; the files must share one grid. North-up GeoTIFFs with a CRS, over the continental US."}
              </p>

              {rasters.length > 0 && (
                <div className="overflow-x-auto rounded-md border">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/40 text-muted-foreground">
                      <tr>
                        <th className="px-2 py-1.5 text-left font-medium">File</th>
                        <th className="px-2 py-1.5 text-left font-medium">Grid</th>
                        {temporal === "yearly" && (
                          <th className="px-2 py-1.5 text-left font-medium">Year</th>
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {rasters.map((r, i) => (
                        <tr key={r.file.name + i} className="border-t">
                          <td className="max-w-[14rem] truncate px-2 py-1.5" title={r.file.name}>
                            {r.file.name}
                          </td>
                          <td className="px-2 py-1.5 text-muted-foreground">
                            {r.error ? (
                              <span className="text-destructive">{r.error}</span>
                            ) : r.meta ? (
                              `${r.meta.width.toLocaleString()} × ${r.meta.height.toLocaleString()} · ${r.meta.resolution_label} · ${r.meta.crs}`
                            ) : (
                              <Loader2 className="inline size-3 animate-spin" />
                            )}
                          </td>
                          {temporal === "yearly" && (
                            <td className="px-2 py-1">
                              <Input
                                value={r.year}
                                onChange={(e) =>
                                  setRasters((prev) =>
                                    prev.map((p, j) => (j === i ? { ...p, year: e.target.value } : p)),
                                  )
                                }
                                inputMode="numeric"
                                maxLength={4}
                                placeholder="YYYY"
                                className="h-7 w-20 text-xs"
                              />
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {gridMismatch && (
                <p className="text-xs text-destructive">
                  These files are on different grids (size, resolution or CRS
                  differ). Every year must share one grid.
                </p>
              )}
              {temporal === "yearly" && rasters.length > 0 && !yearsOk && (
                <p className="text-xs text-destructive">
                  Give every file a distinct four-digit year.
                </p>
              )}
              {temporal === "static" && rasters.length > 1 && (
                <p className="text-xs text-destructive">
                  A time-invariant exposure is one file. Choose &ldquo;Varies by
                  year&rdquo; above to upload several.
                </p>
              )}
            </section>
          )}

          {/* 3. mapping */}
          {kind === "table" && preview && (
            <section className="space-y-3">
              <Label>4. Which column is which?</Label>

              <div className={cn("grid gap-3", temporal === "yearly" && "sm:grid-cols-2")}>
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">
                    Geography code
                  </span>
                  <select
                    value={keyCol}
                    onChange={(e) => setKeyCol(e.target.value)}
                    className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                  >
                    <option value="">Select a column…</option>
                    {preview.columns.map((c) => (
                      <option key={c.name} value={c.name}>{c.name}</option>
                    ))}
                  </select>
                </div>
                {temporal === "yearly" && (
                  <div className="space-y-1">
                    <span className="text-xs text-muted-foreground">Year</span>
                    <select
                      value={yearCol}
                      onChange={(e) => setYearCol(e.target.value)}
                      className={cn(
                        "w-full rounded-md border bg-background px-2 py-1.5 text-sm",
                        yearCol === NO_YEAR && "border-destructive/60",
                      )}
                    >
                      <option value={NO_YEAR}>Select the year column…</option>
                      {preview.columns.map((c) => (
                        <option key={c.name} value={c.name}>{c.name}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              <div className="space-y-1">
                <span className="text-xs text-muted-foreground">
                  Value columns to compute ({valueCols.length} selected)
                </span>
                <div className="max-h-64 overflow-y-auto rounded-md border p-1">
                  {preview.columns
                    .filter((c) => !reserved.has(c.name))
                    .map((c) => {
                      const checked = valueCols.includes(c.name);
                      return (
                        <div key={c.name} className="rounded hover:bg-muted/60">
                          <label className="flex cursor-pointer items-center gap-2 px-2 py-1">
                            <Checkbox
                              checked={checked}
                              onCheckedChange={(next) =>
                                toggleValueCol(c.name, next === true)
                              }
                            />
                            <span className="min-w-0 flex-1 truncate text-sm">
                              {c.name}
                            </span>
                            {!c.numeric && (
                              <span className="shrink-0 text-xs text-muted-foreground">
                                not numeric
                              </span>
                            )}
                          </label>
                          {checked && (
                            <div className="grid gap-2 px-2 pb-2 pl-8 sm:grid-cols-2">
                              <Input
                                value={colLabels[c.name] ?? ""}
                                onChange={(e) =>
                                  setColLabels((m) => ({ ...m, [c.name]: e.target.value }))
                                }
                                maxLength={80}
                                placeholder="Display name (optional)"
                                className="h-8 text-xs"
                              />
                              <Input
                                value={colUnits[c.name] ?? ""}
                                onChange={(e) =>
                                  setColUnits((m) => ({ ...m, [c.name]: e.target.value }))
                                }
                                maxLength={50}
                                placeholder="Unit (optional), e.g. index, ug/m3"
                                className="h-8 text-xs"
                              />
                            </div>
                          )}
                        </div>
                      );
                    })}
                </div>
              </div>
            </section>
          )}

          {kind === "raster" && rasters.length > 0 && (
            <section className="space-y-3">
              <Label>4. What do the pixels hold?</Label>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">Result column</span>
                  <Input
                    value={rasterCol}
                    onChange={(e) => setRasterCol(e.target.value)}
                    maxLength={40}
                    placeholder="e.g. ndvi"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">Display name (optional)</span>
                  <Input
                    value={rasterLabel}
                    onChange={(e) => setRasterLabel(e.target.value)}
                    maxLength={80}
                    placeholder="e.g. Greenness"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">Unit (optional)</span>
                  <Input
                    value={rasterUnit}
                    onChange={(e) => setRasterUnit(e.target.value)}
                    maxLength={50}
                    placeholder="e.g. index"
                    className="h-8 text-xs"
                  />
                </div>
              </div>
              {firstMeta && firstMeta.band_count > 1 && (
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">
                    Band (the files have {firstMeta.band_count})
                  </span>
                  <select
                    value={band}
                    onChange={(e) => setBand(Number(e.target.value))}
                    className="rounded-md border bg-background px-2 py-1.5 text-sm"
                  >
                    {firstMeta.bands.map((b) => (
                      <option key={b.index} value={b.index}>
                        {b.index}{b.description ? ` — ${b.description}` : ""} ({b.dtype})
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {!COLUMN_NAME.test(rasterCol.trim()) && (
                <p className="text-xs text-destructive">
                  The result column must start with a letter and use only letters,
                  digits and underscores.
                </p>
              )}
            </section>
          )}

          {/* 4. naming */}
          {showNaming && (
            <section className="space-y-3">
              <Label>5. How should it appear in the catalog?</Label>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground">Name</span>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={80}
                  placeholder="e.g. Neighborhood greenness"
                />
              </div>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground">
                  Description (optional)
                </span>
                <Textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={400}
                  rows={2}
                  placeholder="What the values mean and where they came from."
                />
              </div>
            </section>
          )}

          {error && (
            <div className="flex gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {showNaming && (
            <p className="text-xs text-muted-foreground">
              {kind === "table"
                ? "Codes are checked for the right shape now; how many actually match the boundary layer is reported in the task log after the first run."
                : "The grid is checked now; how many of the cohort's cells hold data (rather than nodata) is reported in the task log after the first run."}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={!canSave}>
            {busy === "save" && <Loader2 className="size-4 animate-spin" />}
            Save to my exposomes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
