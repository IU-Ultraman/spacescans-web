"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import {
  MAX_DESCRIPTION,
  MAX_NAME,
  MAX_SHORT_FIELD,
  metadataPatch,
  nameProblem,
  type DatasetVariable,
  type RegisteredDataset,
} from "@/lib/datasets";

interface Form {
  name: string;
  description: string;
  source: string;
  version: string;
  license_note: string;
  variables: DatasetVariable[];
}

function formOf(d: RegisteredDataset): Form {
  return {
    name: d.name ?? "",
    description: d.description ?? "",
    source: d.source ?? "",
    version: d.version ?? "",
    license_note: d.license_note ?? "",
    variables: d.variables.map((v) => ({ ...v, unit: v.unit ?? "", description: v.description ?? "" })),
  };
}

/**
 * Edit what a dataset says about itself. Result-column names stay as they
 * are (finished tasks and their results use them); their units and
 * descriptions can change. Only the fields that changed are sent.
 */
export function DatasetEditDialog({
  dataset,
  open,
  onOpenChange,
  onSaved,
}: {
  dataset: RegisteredDataset | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (updated: RegisteredDataset | null) => void | Promise<void>;
}) {
  const [base, setBase] = useState<RegisteredDataset | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<{ message: string; issues: string[] } | null>(null);

  // Re-initialise only when the dialog opens or another dataset is chosen:
  // the parent may hand a fresh summary object at any time (list polling),
  // which must not wipe what the user is typing.
  const datasetRef = useRef(dataset);
  datasetRef.current = dataset;
  const datasetId = dataset?.id ?? null;
  useEffect(() => {
    const summary = datasetRef.current;
    if (!open || !summary) return;
    let cancelled = false;
    setError(null);
    setBase(summary);
    setForm(formOf(summary));
    setLoading(true);
    // The list carries a summary; edit against the full record.
    api
      .getDataset(summary.id)
      .then((full) => {
        if (cancelled) return;
        const merged = { ...full, ...summary, ...pickDetail(full) };
        setBase(merged);
        setForm(formOf(merged));
      })
      .catch(() => {
        /* keep the summary; the server checks the patch anyway */
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [open, datasetId]);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => (f ? { ...f, [k]: v } : f));
  const setVar = (i: number, patch: Partial<DatasetVariable>) =>
    setForm((f) => (f ? { ...f, variables: f.variables.map((v, j) => (j === i ? { ...v, ...patch } : v)) } : f));

  const problem = form ? nameProblem(form.name) : null;

  const save = async () => {
    if (!base || !form) return;
    const patch = metadataPatch(base, {
      ...form,
      variables: form.variables,
    });
    if (Object.keys(patch).length === 0) {
      onOpenChange(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateDataset(base.id, patch);
      await onSaved(updated);
      onOpenChange(false);
    } catch (e) {
      setError(
        e instanceof ApiError ? { message: e.message, issues: e.issues } : { message: "Could not save the changes.", issues: [] },
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit dataset</DialogTitle>
          <DialogDescription>
            Changes apply to tasks you start from now on; finished tasks keep the
            definition they ran with.
          </DialogDescription>
        </DialogHeader>

        {!form ? null : (
          <div className="space-y-4">
            {loading && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" /> Loading the full record…
              </div>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor="edit-name">Name</Label>
                <Input id="edit-name" value={form.name} onChange={(e) => set("name", e.target.value)} maxLength={MAX_NAME} />
                {problem && <p className="text-xs text-destructive">{problem}</p>}
              </div>
              <div className="space-y-1">
                <Label htmlFor="edit-source">Source</Label>
                <Input id="edit-source" value={form.source} onChange={(e) => set("source", e.target.value)} maxLength={MAX_SHORT_FIELD} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="edit-version">Version</Label>
                <Input id="edit-version" value={form.version} onChange={(e) => set("version", e.target.value)} maxLength={MAX_SHORT_FIELD} />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor="edit-description">Description</Label>
                <Textarea id="edit-description" value={form.description} onChange={(e) => set("description", e.target.value)} maxLength={MAX_DESCRIPTION} rows={2} />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor="edit-terms">Terms of use</Label>
                <Input id="edit-terms" value={form.license_note} onChange={(e) => set("license_note", e.target.value)} maxLength={MAX_SHORT_FIELD} />
              </div>
            </div>

            {form.variables.length > 0 && (
              <div className="space-y-1">
                <Label>Result columns</Label>
                <div className="max-h-64 space-y-2 overflow-y-auto rounded-md border p-2">
                  {form.variables.map((v, i) => (
                    <div key={v.name} className="grid items-center gap-2 sm:grid-cols-[10rem_8rem_1fr]">
                      <code className="truncate text-xs" title={v.name}>{v.name}</code>
                      <Input
                        value={v.unit ?? ""}
                        onChange={(e) => setVar(i, { unit: e.target.value })}
                        maxLength={50}
                        placeholder="Unit"
                        aria-label={`Unit of ${v.name}`}
                        className="h-8 text-xs"
                      />
                      <Input
                        value={v.description ?? ""}
                        onChange={(e) => setVar(i, { description: e.target.value })}
                        maxLength={MAX_SHORT_FIELD}
                        placeholder="What it measures"
                        aria-label={`Description of ${v.name}`}
                        className="h-8 text-xs"
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {error && (
              <div className="flex gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />
                <div className="min-w-0 space-y-1">
                  <p>{error.message}</p>
                  {error.issues.length > 0 && (
                    <ul className="list-disc space-y-0.5 pl-4">
                      {error.issues.map((issue, i) => <li key={i}>{issue}</li>)}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={!form || !!problem || saving}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Fields only the full record carries; they win over the summary's blanks. */
function pickDetail(full: RegisteredDataset): Partial<RegisteredDataset> {
  const out: Partial<RegisteredDataset> = {};
  for (const k of ["source", "version", "description", "license_note"] as const) {
    if (full[k] != null) out[k] = full[k];
  }
  if (full.variables.length) out.variables = full.variables;
  return out;
}
