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
  type CustomBoundary, type CustomExposome, type CustomPreview,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const NO_YEAR = "__none__";

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
 * Upload a CSV, say which column is the geography and which hold values, save.
 *
 * The column mapping is a form rather than guesswork: a wrong guess produces a
 * dataset that links nothing, and the server can only check the *shape* of a
 * geography key, never its membership in the real key universe.
 */
export function CustomExposomeDialog({
  open, onOpenChange, onCreated,
}: CustomExposomeDialogProps) {
  const [boundaries, setBoundaries] = useState<CustomBoundary[] | null>(null);
  const [boundary, setBoundary] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<CustomPreview | null>(null);
  const [keyCol, setKeyCol] = useState("");
  const [yearCol, setYearCol] = useState<string>(NO_YEAR);
  const [valueCols, setValueCols] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  // Per value column. One dataset can carry a greenness index next to a
  // temperature, so a single dataset-level unit cannot be right.
  const [colLabels, setColLabels] = useState<Record<string, string>>({});
  const [colUnits, setColUnits] = useState<Record<string, string>>({});
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
    setFile(null); setPreview(null); setKeyCol(""); setYearCol(NO_YEAR);
    setValueCols([]); setName(""); setDescription("");
    setColLabels({}); setColUnits({});
    setError(null); setBusy(null);
  };

  const close = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

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

  const canSave =
    !!file && !!preview && !!boundary && !!keyCol && valueCols.length > 0 &&
    name.trim().length > 0 && busy === null;

  const save = async () => {
    if (!file) return;
    setBusy("save");
    setError(null);
    try {
      const created = await api.createCustomExposome({
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
      await onCreated(created);
      close(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the dataset");
    } finally {
      setBusy(null);
    }
  };

  const reserved = new Set([keyCol, yearCol === NO_YEAR ? "" : yearCol]);

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add a custom exposome</DialogTitle>
          <DialogDescription>
            Upload a CSV of your own values, one row per Census geography
            (optionally per year). It becomes selectable for any of your tasks.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          {/* 1. boundary */}
          <section className="space-y-2">
            <Label>1. Which geography are your values keyed by?</Label>
            {boundaries === null ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" /> Checking what this
                deployment provides…
              </div>
            ) : available.length === 0 ? (
              <p className="text-xs text-destructive">
                This deployment has no boundary data provisioned, so a custom
                exposome could not be computed. Add a boundary dataset on the
                Data Setup page first.
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
          </section>

          {/* 2. file */}
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

          {/* 3. mapping */}
          {preview && (
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

          {/* 4. naming */}
          {preview && (
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

          {preview && (
            <p className="text-xs text-muted-foreground">
              Codes are checked for the right shape now; how many actually match
              the boundary layer is reported in the task log after the first run.
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
