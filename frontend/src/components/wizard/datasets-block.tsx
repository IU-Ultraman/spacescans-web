"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Loader2, Plus, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { DatasetBadges } from "@/components/datasets/dataset-badges";
import { DatasetUploadDialog } from "@/components/datasets/dataset-upload-dialog";
import { api, ApiError } from "@/lib/api";
import { isPending, isSelectable, sortDatasets, type RegisteredDataset } from "@/lib/datasets";
import { cn } from "@/lib/utils";

interface DatasetsBlockProps {
  /** Ids of the selected registered datasets. */
  selected: string[];
  onSelectionChange: (ids: string[]) => void;
  /** Every dataset the user can select, whenever the list (re)loads. */
  onLoaded?: (datasets: RegisteredDataset[]) => void;
  /** Show a dataset in the detail panel. */
  onFocus?: (dataset: RegisteredDataset | null) => void;
  focusedId?: string | null;
}

/**
 * "Your datasets" in the Select Exposures step: the user's registered
 * datasets plus those shared with the deployment, listed below the ontology
 * tree (they have no ontology node). Selection only; adding is allowed here
 * too, everything else lives on the My datasets page.
 */
export function DatasetsBlock({
  selected,
  onSelectionChange,
  onLoaded,
  onFocus,
  focusedId,
}: DatasetsBlockProps) {
  const [datasets, setDatasets] = useState<RegisteredDataset[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  // Latest callbacks and selection, read by load() without re-creating it.
  const latest = useRef({ selected, onSelectionChange, onLoaded });
  latest.current = { selected, onSelectionChange, onLoaded };

  const load = useCallback(async (select?: string) => {
    try {
      const list = sortDatasets(await api.listDatasets());
      setDatasets(list);
      setError(null);
      latest.current.onLoaded?.(list);
      // A selected dataset that was deleted (or unshared) since cannot run:
      // drop it, and add the one just created.
      const usable = new Set(list.filter(isSelectable).map((d) => d.id));
      const prev = latest.current.selected;
      const next = prev.filter((id) => usable.has(id));
      if (select && list.some((d) => d.id === select) && !next.includes(select)) next.push(select);
      if (next.length !== prev.length || next.some((id, i) => id !== prev[i])) {
        latest.current.onSelectionChange(next);
      }
      return list;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load your datasets");
      setDatasets((prev) => prev ?? []);
      return null;
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const anyPending = datasets?.some(isPending) ?? false;
  useEffect(() => {
    if (!anyPending) return;
    const t = setInterval(() => void load(), 5000);
    return () => clearInterval(t);
  }, [anyPending, load]);

  const toggle = (id: string, checked: boolean) =>
    onSelectionChange(checked ? [...selected.filter((s) => s !== id), id] : selected.filter((s) => s !== id));

  return (
    <div className="mt-3 rounded-lg border">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <div className="min-w-0">
          <div className="text-sm font-medium">Your datasets</div>
          <div className="truncate text-xs text-muted-foreground">
            Registered by you, or shared with everyone here ·{" "}
            <Link href="/dashboard/datasets" className="underline-offset-2 hover:text-foreground hover:underline">
              manage
            </Link>
          </div>
        </div>
        <Button size="sm" variant="outline" onClick={() => setAdding(true)} className="shrink-0">
          <Plus className="size-4" /> Add
        </Button>
      </div>

      {error && <div className="px-3 py-2 text-xs text-destructive">{error}</div>}

      {datasets === null ? (
        <div className="flex items-center gap-2 px-3 py-4 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" /> Loading…
        </div>
      ) : datasets.length === 0 ? (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="flex w-full items-center gap-2 px-3 py-4 text-left text-xs text-muted-foreground hover:bg-muted/60"
        >
          <Upload className="size-3.5 shrink-0" />
          Add your own area table, raster or map features to compute them for your
          cohort next to the catalog exposures.
        </button>
      ) : (
        <div className="max-h-64 overflow-y-auto p-1">
          {datasets.map((d) => {
            const usable = isSelectable(d);
            const isSelected = selected.includes(d.id);
            return (
              <div
                key={d.id}
                className={cn(
                  "flex items-start gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-muted/60",
                  (isSelected || focusedId === d.id) && "bg-primary/5",
                )}
              >
                <Checkbox
                  checked={isSelected}
                  disabled={!usable}
                  onCheckedChange={(checked) => {
                    toggle(d.id, checked === true);
                    onFocus?.(d);
                  }}
                  aria-label={`Select ${d.name}`}
                  className="mt-0.5 shrink-0"
                />
                <button
                  type="button"
                  onClick={() => onFocus?.(d)}
                  className="min-w-0 flex-1 text-left"
                  title={d.description ?? undefined}
                >
                  <div className="truncate text-sm text-foreground/90">{d.name}</div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-1">
                    <DatasetBadges dataset={d} />
                    {!d.owned_by_me && (
                      <span className="text-[10px] text-muted-foreground">
                        shared by {d.owner_display || "another user"}
                      </span>
                    )}
                  </div>
                </button>
              </div>
            );
          })}
        </div>
      )}

      <DatasetUploadDialog
        open={adding}
        onOpenChange={setAdding}
        onCreated={async (created) => {
          const list = await load(created && isSelectable(created) ? created.id : undefined);
          const fresh = created ? list?.find((d) => d.id === created.id) ?? created : null;
          if (fresh) onFocus?.(fresh);
        }}
      />
    </div>
  );
}
