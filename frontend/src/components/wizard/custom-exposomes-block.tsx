"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { api, ApiError, type CustomExposome } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CustomExposomeDialog } from "./custom-exposome-dialog";

interface CustomExposomesBlockProps {
  /** Currently selected variable keys (shipped + custom). */
  selected: string[];
  /** Called with the next full selection when a custom row is toggled. */
  onSelectionChange: (keys: string[]) => void;
  /** Focus a dataset so the detail panel can describe it. */
  onFocus?: (dataset: CustomExposome | null) => void;
  focusedKey?: string | null;
}

/**
 * "My Exposomes" — the user's uploaded datasets, listed below the ontology
 * tree rather than inside it. They have no ontology node to hang from, and
 * injecting synthetic nodes into the tree would entangle this with the
 * auto-expand pass; a separate block keeps the tree untouched.
 */
export function CustomExposomesBlock({
  selected,
  onSelectionChange,
  onFocus,
  focusedKey,
}: CustomExposomesBlockProps) {
  const [datasets, setDatasets] = useState<Record<string, CustomExposome> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.listCustomExposomes();
      setDatasets(res.variables);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load your exposomes");
      setDatasets({});
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (key: string, checked: boolean) => {
    onSelectionChange(
      checked ? [...selected, key] : selected.filter((k) => k !== key),
    );
  };

  const remove = async (dataset: CustomExposome) => {
    setDeleting(dataset.dataset_id);
    try {
      await api.deleteCustomExposome(dataset.dataset_id);
      // Drop it from the selection too — a deleted dataset cannot run, and the
      // config endpoint would reject the key.
      onSelectionChange(selected.filter((k) => k !== dataset.variable_key));
      if (focusedKey === dataset.variable_key) onFocus?.(null);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Delete failed");
    } finally {
      setDeleting(null);
    }
  };

  const rows = Object.values(datasets ?? {});

  return (
    <div className="mt-3 rounded-lg border">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <div className="min-w-0">
          <div className="text-sm font-medium">My Exposomes</div>
          <div className="truncate text-xs text-muted-foreground">
            Your own values — by polygon (CSV) or as a raster (GeoTIFF)
          </div>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setDialogOpen(true)}
          className="shrink-0"
        >
          <Plus className="size-4" /> Add
        </Button>
      </div>

      {error && (
        <div className="px-3 py-2 text-xs text-destructive">{error}</div>
      )}

      {datasets === null ? (
        <div className="flex items-center gap-2 px-3 py-4 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" /> Loading…
        </div>
      ) : rows.length === 0 ? (
        <button
          type="button"
          onClick={() => setDialogOpen(true)}
          className="flex w-full items-center gap-2 px-3 py-4 text-left text-xs text-muted-foreground hover:bg-muted/60"
        >
          <Upload className="size-3.5 shrink-0" />
          Upload a CSV of area-level values, or a GeoTIFF, to compute it for
          your cohort alongside the exposures above.
        </button>
      ) : (
        <div className="max-h-56 overflow-y-auto p-1">
          {rows.map((dataset) => {
            const isSelected = selected.includes(dataset.variable_key);
            const isFocused = focusedKey === dataset.variable_key;
            return (
              <div
                key={dataset.dataset_id}
                className={cn(
                  "group flex items-center gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-muted/60",
                  (isSelected || isFocused) && "bg-primary/5",
                )}
              >
                <Checkbox
                  checked={isSelected}
                  onCheckedChange={(checked) => {
                    toggle(dataset.variable_key, checked === true);
                    onFocus?.(dataset);
                  }}
                  className="shrink-0"
                />
                <button
                  type="button"
                  onClick={() => onFocus?.(dataset)}
                  className="min-w-0 flex-1 text-left"
                  title={dataset.description}
                >
                  <div className="truncate text-sm text-foreground/90">
                    {dataset.label}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {dataset.geometry === "raster"
                      ? `Raster · ${dataset.grid?.resolution_label ?? ""}`
                      : `${dataset.boundary} · ${dataset.value_cols.length} ${
                          dataset.value_cols.length === 1 ? "column" : "columns"
                        }`}{" "}
                    ·{" "}
                    {dataset.temporal === "yearly"
                      ? `${dataset.coverage_years[0]}–${dataset.coverage_years[1]}`
                      : "time-invariant"}
                  </div>
                </button>
                <button
                  type="button"
                  aria-label={`Delete ${dataset.label}`}
                  onClick={() => void remove(dataset)}
                  disabled={deleting === dataset.dataset_id}
                  className="shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:text-destructive focus:opacity-100 group-hover:opacity-100"
                >
                  {deleting === dataset.dataset_id ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="size-3.5" />
                  )}
                </button>
              </div>
            );
          })}
        </div>
      )}

      <CustomExposomeDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onCreated={async (created) => {
          await load();
          onSelectionChange([...selected, created.variable_key]);
          onFocus?.(created);
        }}
      />
    </div>
  );
}
