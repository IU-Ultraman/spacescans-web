"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Database, Loader2, Pencil, Plus, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { DatasetBadges, VisibilityChip } from "@/components/datasets/dataset-badges";
import { DatasetDetail } from "@/components/datasets/dataset-detail";
import { DatasetEditDialog } from "@/components/datasets/dataset-edit-dialog";
import { DatasetUploadDialog } from "@/components/datasets/dataset-upload-dialog";
import { ShareToggle } from "@/components/datasets/share-toggle";
import { api, ApiError } from "@/lib/api";
import { isPending, sortDatasets, type RegisteredDataset } from "@/lib/datasets";
import { cn } from "@/lib/utils";

type Filter = "all" | "mine" | "shared";

/**
 * "My datasets": the user's registered datasets plus the ones other users
 * shared with the whole deployment. Add, edit, share and delete happen here;
 * the task wizard only selects (and can add).
 */
export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<RegisteredDataset[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [detailVersion, setDetailVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<RegisteredDataset | null>(null);
  const [sharingId, setSharingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<RegisteredDataset | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const list = sortDatasets(await api.listDatasets());
      setDatasets(list);
      setLoadError(null);
      return list;
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Could not load your datasets");
      setDatasets((prev) => prev ?? []);
      return null;
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // A dataset is prepared on the server after upload; poll until it is ready.
  const anyPending = datasets?.some(isPending) ?? false;
  useEffect(() => {
    if (!anyPending) return;
    const t = setInterval(() => void load(), 5000);
    return () => clearInterval(t);
  }, [anyPending, load]);

  const mine = datasets?.filter((d) => d.owned_by_me) ?? [];
  const shared = datasets?.filter((d) => !d.owned_by_me) ?? [];
  const visible = filter === "mine" ? mine : filter === "shared" ? shared : (datasets ?? []);
  const focused = visible.find((d) => d.id === focusedId) ?? visible[0] ?? null;

  const replace = (updated: RegisteredDataset) =>
    setDatasets((list) => (list ? sortDatasets(list.map((d) => (d.id === updated.id ? updated : d))) : list));

  const toggleShare = async (d: RegisteredDataset, next: boolean) => {
    const visibility = next ? "deployment" : "private";
    setSharingId(d.id);
    setActionError(null);
    replace({ ...d, visibility });
    try {
      const updated = await api.updateDataset(d.id, { visibility });
      if (updated) replace({ ...updated, owned_by_me: updated.owned_by_me || d.owned_by_me });
      else await load();
    } catch (e) {
      replace(d);
      setActionError(e instanceof ApiError ? e.message : "Could not change who can use it");
    } finally {
      setSharingId(null);
    }
  };

  const remove = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteDataset(confirmDelete.id);
      if (focusedId === confirmDelete.id) setFocusedId(null);
      setConfirmDelete(null);
      await load();
    } catch (e) {
      setDeleteError(e instanceof ApiError ? e.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight text-foreground">My datasets</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Your own exposure data, registered once and selectable in any task: area
            tables, rasters, and point, line or polygon features. Datasets are private
            to you unless you share them with all users of this deployment.
          </p>
        </div>
        <Button onClick={() => setAdding(true)}>
          <Plus className="size-4" /> Add dataset
        </Button>
      </header>

      {loadError && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <span>{loadError}</span>
        </div>
      )}

      {datasets === null ? (
        <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading datasets…
        </div>
      ) : datasets.length === 0 ? (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="flex w-full flex-col items-center gap-3 rounded-xl border-2 border-dashed px-6 py-14 text-center text-sm text-muted-foreground transition-colors hover:bg-muted/30"
        >
          <Upload className="size-8 text-muted-foreground/50" />
          <span className="font-medium text-foreground">No datasets yet</span>
          <span className="max-w-md">
            Add a CSV of area values, GeoTIFF rasters, or a file of map features. It is
            checked and prepared once, then you can select it in any task.
          </span>
        </button>
      ) : (
        <>
          <div className="flex flex-wrap gap-2" role="tablist" aria-label="Which datasets">
            {(
              [
                ["all", `All (${datasets.length})`],
                ["mine", `Yours (${mine.length})`],
                ["shared", `Shared with you (${shared.length})`],
              ] as [Filter, string][]
            ).map(([f, label]) => (
              <button
                key={f}
                type="button"
                role="tab"
                aria-selected={filter === f}
                onClick={() => setFilter(f)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs transition-colors",
                  filter === f ? "border-primary bg-primary/10 text-foreground" : "text-muted-foreground hover:bg-muted/60",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="flex flex-col gap-5 md:flex-row">
            <div className="md:w-2/5 md:shrink-0">
              <div className="max-h-[36rem] overflow-y-auto rounded-lg border p-1">
                {visible.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => {
                      setFocusedId(d.id);
                      setActionError(null);
                    }}
                    className={cn(
                      "flex w-full items-start gap-2 rounded-md px-3 py-2 text-left transition-colors hover:bg-muted/60",
                      focused?.id === d.id && "bg-primary/5 ring-1 ring-primary/20",
                    )}
                  >
                    <Database className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-foreground/90">{d.name}</span>
                      <span className="mt-1 flex flex-wrap items-center gap-1">
                        <DatasetBadges dataset={d} />
                        <VisibilityChip dataset={d} />
                      </span>
                      <span className="mt-1 block truncate text-xs text-muted-foreground">
                        {d.variables.length} result column{d.variables.length === 1 ? "" : "s"}
                        {d.variables.length > 0 && `: ${d.variables.map((v) => v.name).join(", ")}`}
                      </span>
                    </span>
                  </button>
                ))}
                {visible.length === 0 && (
                  <p className="px-3 py-6 text-center text-xs text-muted-foreground">
                    {filter === "shared" ? "No one has shared a dataset with this deployment yet." : "None here."}
                  </p>
                )}
              </div>
            </div>

            <div className="min-w-0 flex-1">
              {focused ? (
                <DatasetDetail
                  key={`${focused.id}-${detailVersion}`}
                  dataset={focused}
                  actions={
                    focused.owned_by_me ? (
                      <div className="space-y-3 rounded-md border bg-muted/20 p-3">
                        <ShareToggle
                          checked={focused.visibility === "deployment"}
                          onChange={(next) => void toggleShare(focused, next)}
                          busy={sharingId === focused.id}
                        />
                        <div className="flex flex-wrap gap-2">
                          <Button size="sm" variant="outline" onClick={() => setEditing(focused)}>
                            <Pencil className="size-3.5" /> Edit details
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-destructive hover:text-destructive"
                            onClick={() => {
                              setDeleteError(null);
                              setConfirmDelete(focused);
                            }}
                          >
                            <Trash2 className="size-3.5" /> Delete
                          </Button>
                        </div>
                        {actionError && <p className="text-xs text-destructive">{actionError}</p>}
                      </div>
                    ) : (
                      <p className="rounded-md border bg-muted/20 p-3 text-xs text-muted-foreground">
                        Shared by {focused.owner_display || "another user"}. You can select it in
                        your tasks; only its owner can edit, unshare or delete it.
                      </p>
                    )
                  }
                />
              ) : (
                <div className="rounded-lg border p-5 text-sm text-muted-foreground">Select a dataset to see its details.</div>
              )}
            </div>
          </div>
        </>
      )}

      <DatasetUploadDialog
        open={adding}
        onOpenChange={setAdding}
        onCreated={async (created) => {
          await load();
          if (created) {
            setFilter("all");
            setFocusedId(created.id);
          }
        }}
      />

      <DatasetEditDialog
        dataset={editing}
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
        onSaved={async (updated) => {
          if (updated) replace({ ...updated, owned_by_me: true });
          else await load();
          setDetailVersion((v) => v + 1);
        }}
      />

      <Dialog open={confirmDelete !== null} onOpenChange={(open) => !open && !deleting && setConfirmDelete(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete “{confirmDelete?.name}”?</DialogTitle>
            <DialogDescription>
              It can no longer be selected for new tasks. Finished tasks keep their
              results. Deleting is refused while a queued or running task uses it.
              {confirmDelete?.visibility === "deployment" &&
                " Other users of this deployment lose access to it too."}
            </DialogDescription>
          </DialogHeader>
          {deleteError && <p className="text-sm text-destructive">{deleteError}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(null)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void remove()} disabled={deleting}>
              {deleting && <Loader2 className="size-4 animate-spin" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
