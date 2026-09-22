"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, FileUp, Loader2 } from "lucide-react";
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
    setKind("table");
    setFile(null); setPreview(null); setKeyCol(""); setYearCol(NO_YEAR);
    setValueCols([]); setColLabels({}); setColUnits({});
    setRasters([]); setBand(1); setRasterCol("value"); setRasterLabel(""); setRasterUnit("");
    setName(""); setDescription("");
    setError(null); setBusy(null);
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
      if (year) setYearCol(year.name);
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
      // A four-digit year in the filename is a reasonable first guess when
      // there are several files; a single file is static unless told otherwise.
      year: files.length > 1 ? (f.name.match(/(?:19|20)\d{2}/) ?? [""])[0] : "",
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
    rasters.length <= 1
      ? rasters.length === 0 || rasters[0].year.trim() === "" || /^\d{4}$/.test(rasters[0].year.trim())
      : rasters.every((r) => /^\d{4}$/.test(r.year.trim())) &&
        new Set(rasters.map((r) => r.year.trim())).size === rasters.length;

  // ----------------------------------------------------------------- save ---

  const canSave =
    busy === null &&
    name.trim().length > 0 &&
    (kind === "table"
      ? !!file && !!preview && !!boundary && !!keyCol && valueCols.length > 0
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
          year_col: yearCol === NO_YEAR ? null : yearCol,
        });
      } else {
        created = await api.createCustomRaster({
          files: rasters.map((r) => ({
            file: r.file,
            year: r.year.trim() === "" ? null : Number(r.year.trim()),
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
            tasks — a table keyed by tract, block group, ZIP area or county, or
            a raster.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          {/* 1. kind (+ boundary for a table) */}
          <section className="space-y-2">
            <Label>1. What are you uploading?</Label>
            <div className="flex flex-wrap gap-2">
              {([
                ["table", "Table (CSV)"],
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
                  Which geography are the rows keyed by?
                </span>
                {boundaries === null ? (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className="size-3.5 animate-spin" /> Checking what this
                    deployment provides…
                  </div>
                ) : available.length === 0 ? (
                  <p className="text-xs text-destructive">
                    This deployment has no boundary data provisioned, so a table
                    could not be computed. Add a boundary dataset on the Data Setup
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

          {/* 2. file(s) */}
          {kind === "table" ? (
            <section className="space-y-2">
              <Label htmlFor="custom-file">2. Your CSV</Label>
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
              <Label htmlFor="custom-rasters">2. Your GeoTIFF(s)</Label>
              <div className="flex items-center gap-3">
                <Input
                  id="custom-rasters"
                  type="file"
                  accept=".tif,.tiff"
                  multiple
                  onChange={(e) => void pickRasters(e.target.files)}
                  className="cursor-pointer"
                />
                {busy === "preview" && (
                  <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                One file = a time-invariant exposure. Several files, one per year,
                = a yearly exposure; they must share one grid. North-up GeoTIFFs
                with a CRS, over the continental US.
              </p>

              {rasters.length > 0 && (
                <div className="overflow-x-auto rounded-md border">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/40 text-muted-foreground">
                      <tr>
                        <th className="px-2 py-1.5 text-left font-medium">File</th>
                        <th className="px-2 py-1.5 text-left font-medium">Grid</th>
                        <th className="px-2 py-1.5 text-left font-medium">
                          Year{rasters.length === 1 ? " (blank = none)" : ""}
                        </th>
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
                              placeholder={rasters.length === 1 ? "—" : "YYYY"}
                              className="h-7 w-20 text-xs"
                            />
                          </td>
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
              {rasters.length > 1 && !yearsOk && (
                <p className="text-xs text-destructive">
                  Give every file a distinct four-digit year.
                </p>
              )}
            </section>
          )}

          {/* 3. mapping */}
          {kind === "table" && preview && (
            <section className="space-y-3">
              <Label>3. Which column is which?</Label>

              <div className="grid gap-3 sm:grid-cols-2">
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
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">
                    Year (leave empty if the values do not vary by year)
                  </span>
                  <select
                    value={yearCol}
                    onChange={(e) => setYearCol(e.target.value)}
                    className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                  >
                    <option value={NO_YEAR}>No year column</option>
                    {preview.columns.map((c) => (
                      <option key={c.name} value={c.name}>{c.name}</option>
                    ))}
                  </select>
                </div>
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
              <Label>3. What do the pixels hold?</Label>
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
              <Label>4. How should it appear in the catalog?</Label>
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
