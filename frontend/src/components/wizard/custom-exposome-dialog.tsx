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

// Names the runner already uses in the value table or in result.csv; the
// server refuses them too (compared ignoring case).
const RESERVED_RASTER_COLS = new Set(["grid_id", "year", "pid", "episode_id", "patid", "geoid"]);
// One result column per band, capped like a table's value columns.
const MAX_RASTER_BANDS = 40;

/** A first guess at a band's result column: its description made column-safe,
 *  else "value" for a one-band file, else band_<n>. */
function bandColumn(index: number, description: string, single: boolean): string {
  const s = description.trim().replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);
  if (s) return /^[A-Za-z]/.test(s) ? s : `b_${s}`.slice(0, 40);
  return single ? "value" : `band_${index}`;
}

/** Why a band's column name would be refused, or null. `others` are the
 *  names of the other selected bands. */
function bandColumnProblem(col: string, others: string[]): string | null {
  const c = col.trim();
  if (!COLUMN_NAME.test(c)) return "Start with a letter; use only letters, digits and underscores.";
  if (RESERVED_RASTER_COLS.has(c.toLowerCase())) return `"${c}" is already a column in result.csv.`;
  if (others.some((o) => o.trim().toLowerCase() === c.toLowerCase())) {
    return "Another band has this name (names are compared ignoring case).";
  }
  return null;
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
          One band, or several: each band you choose becomes its own result
          column. Set a nodata value for cells without data.
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
  // Bands to link, kept in band order; per band its result column, display
  // name and unit, the way a table keeps them per value column.
  const [bands, setBands] = useState<number[]>([1]);
  const [bandCols, setBandCols] = useState<Record<number, string>>({ 1: "value" });
  const [bandLabels, setBandLabels] = useState<Record<number, string>>({});
  const [bandUnits, setBandUnits] = useState<Record<number, string>>({});

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
    setRasters([]); setBands([1]); setBandCols({ 1: "value" }); setBandLabels({}); setBandUnits({});
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
    let named = false;
    for (let i = 0; i < picks.length; i++) {
      try {
        const meta = await api.previewCustomRaster(picks[i].file);
        setRasters((prev) => prev.map((p, j) => (j === i ? { ...p, meta } : p)));
        if (!named) {
          // First readable file: one suggested column per band, band 1 selected.
          named = true;
          const single = meta.band_count === 1;
          const cols: Record<number, string> = {};
          const used = new Set<string>();
          for (const b of meta.bands) {
            let c = bandColumn(b.index, b.description, single);
            if (used.has(c.toLowerCase())) c = `${c}_${b.index}`.slice(0, 40);
            used.add(c.toLowerCase());
            cols[b.index] = c;
          }
          setBands([1]); setBandCols(cols); setBandUnits({});
          setBandLabels(Object.fromEntries(
            meta.bands.filter((b) => b.description).map((b) => [b.index, b.description.slice(0, 80)]),
          ));
        }
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

  // Bands every file has: a yearly dataset reads the same bands from each year.
  const bandChoices = useMemo(() => {
    const metas = rasters.filter((r) => r.meta).map((r) => r.meta!);
    if (!metas.length) return [];
    const common = Math.min(...metas.map((m) => m.band_count));
    return metas[0].bands.filter((b) => b.index <= common);
  }, [rasters]);
  const bandCountDiffers = useMemo(() => {
    const counts = new Set(rasters.filter((r) => r.meta).map((r) => r.meta!.band_count));
    return counts.size > 1;
  }, [rasters]);
  const chosenBands = bands.filter((b) => bandChoices.some((c) => c.index === b));
  const bandProblems: Record<number, string | null> = Object.fromEntries(
    chosenBands.map((b) => [
      b,
      bandColumnProblem(bandCols[b] ?? "", chosenBands.filter((o) => o !== b).map((o) => bandCols[o] ?? "")),
    ]),
  );
  const bandsOk =
    chosenBands.length > 0 &&
    chosenBands.length <= MAX_RASTER_BANDS &&
    chosenBands.every((b) => bandProblems[b] === null);
  const toggleBand = (index: number, checked: boolean) =>
    setBands((prev) =>
      checked ? [...prev.filter((b) => b !== index), index].sort((a, b) => a - b)
              : prev.filter((b) => b !== index),
    );

  // ----------------------------------------------------------------- save ---

  const canSave =
    busy === null &&
    name.trim().length > 0 &&
    (kind === "table"
      ? !!file && !!preview && !!boundary && !!keyCol && valueCols.length > 0 &&
        (temporal === "static" || yearCol !== NO_YEAR)
      : rastersReady && yearsOk && bandsOk);

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
        const cols = chosenBands.map((b) => (bandCols[b] ?? "").trim());
        const byCol = (m: Record<number, string>) =>
          Object.fromEntries(chosenBands.map((b, i) => [cols[i], m[b] ?? ""]));
        created = await api.createCustomRaster({
          files: rasters.map((r) => ({
            file: r.file,
            year: temporal === "yearly" ? Number(r.year.trim()) : null,
          })),
          name: name.trim(),
          bands: chosenBands,
          value_cols: cols,
          description,
          value_labels: pick(byCol(bandLabels), cols),
          value_units: pick(byCol(bandUnits), cols),
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
              {bandChoices.length <= 1 ? (
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="space-y-1">
                    <span className="text-xs text-muted-foreground">Result column</span>
                    <Input
                      value={bandCols[1] ?? ""}
                      onChange={(e) => setBandCols((m) => ({ ...m, 1: e.target.value }))}
                      maxLength={40}
                      placeholder="e.g. ndvi"
                      className="h-8 text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <span className="text-xs text-muted-foreground">Display name (optional)</span>
                    <Input
                      value={bandLabels[1] ?? ""}
                      onChange={(e) => setBandLabels((m) => ({ ...m, 1: e.target.value }))}
                      maxLength={80}
                      placeholder="e.g. Greenness"
                      className="h-8 text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <span className="text-xs text-muted-foreground">Unit (optional)</span>
                    <Input
                      value={bandUnits[1] ?? ""}
                      onChange={(e) => setBandUnits((m) => ({ ...m, 1: e.target.value }))}
                      maxLength={50}
                      placeholder="e.g. index"
                      className="h-8 text-xs"
                    />
                  </div>
                  {bandProblems[1] && (
                    <p className="text-xs text-destructive sm:col-span-3">{bandProblems[1]}</p>
                  )}
                </div>
              ) : (
                <div className="space-y-1">
                  <div className="flex items-baseline gap-3">
                    <span className="text-xs text-muted-foreground">
                      Bands to compute ({chosenBands.length} of {bandChoices.length} selected;
                      each becomes its own result column)
                    </span>
                    <button
                      type="button"
                      className="ml-auto text-xs text-primary hover:underline"
                      onClick={() =>
                        setBands(bandChoices.slice(0, MAX_RASTER_BANDS).map((b) => b.index))
                      }
                    >
                      Select all
                    </button>
                    <button
                      type="button"
                      className="text-xs text-primary hover:underline"
                      onClick={() => setBands([])}
                    >
                      Clear
                    </button>
                  </div>
                  <div className="max-h-72 overflow-y-auto rounded-md border p-1">
                    {bandChoices.map((b) => {
                      const checked = chosenBands.includes(b.index);
                      const problem = checked ? bandProblems[b.index] : null;
                      return (
                        <div key={b.index} className="rounded hover:bg-muted/60">
                          <label className="flex cursor-pointer items-center gap-2 px-2 py-1">
                            <Checkbox
                              checked={checked}
                              onCheckedChange={(next) => toggleBand(b.index, next === true)}
                            />
                            <span className="min-w-0 flex-1 truncate text-sm">
                              Band {b.index}
                              {b.description && (
                                <span className="text-muted-foreground"> · {b.description}</span>
                              )}
                            </span>
                            <span className="shrink-0 text-xs text-muted-foreground">{b.dtype}</span>
                          </label>
                          {checked && (
                            <div className="space-y-1 px-2 pb-2 pl-8">
                              <div className="grid gap-2 sm:grid-cols-3">
                                <Input
                                  value={bandCols[b.index] ?? ""}
                                  onChange={(e) =>
                                    setBandCols((m) => ({ ...m, [b.index]: e.target.value }))
                                  }
                                  maxLength={40}
                                  placeholder="Result column, e.g. pm25"
                                  aria-label={`Result column for band ${b.index}`}
                                  className={cn("h-8 text-xs", problem && "border-destructive/60")}
                                />
                                <Input
                                  value={bandLabels[b.index] ?? ""}
                                  onChange={(e) =>
                                    setBandLabels((m) => ({ ...m, [b.index]: e.target.value }))
                                  }
                                  maxLength={80}
                                  placeholder="Display name (optional)"
                                  aria-label={`Display name for band ${b.index}`}
                                  className="h-8 text-xs"
                                />
                                <Input
                                  value={bandUnits[b.index] ?? ""}
                                  onChange={(e) =>
                                    setBandUnits((m) => ({ ...m, [b.index]: e.target.value }))
                                  }
                                  maxLength={50}
                                  placeholder="Unit (optional)"
                                  aria-label={`Unit for band ${b.index}`}
                                  className="h-8 text-xs"
                                />
                              </div>
                              {problem && <p className="text-xs text-destructive">{problem}</p>}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  {chosenBands.length === 0 && (
                    <p className="text-xs text-destructive">Select at least one band.</p>
                  )}
                  {chosenBands.length > MAX_RASTER_BANDS && (
                    <p className="text-xs text-destructive">
                      At most {MAX_RASTER_BANDS} bands per dataset.
                    </p>
                  )}
                  {firstMeta && firstMeta.band_count > firstMeta.bands.length && (
                    <p className="text-xs text-muted-foreground">
                      The files have {firstMeta.band_count} bands; the first{" "}
                      {firstMeta.bands.length} are listed.
                    </p>
                  )}
                  {bandCountDiffers && (
                    <p className="text-xs text-muted-foreground">
                      The files have different numbers of bands; only bands every
                      file has are listed.
                    </p>
                  )}
                </div>
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
            Save to custom exposomes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
