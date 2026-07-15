"use client";

import { useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import { useVariableCatalog } from "@/lib/use-variable-catalog";
import { useColumnMeta } from "@/lib/use-column-meta";
import {
  BOUNDARY_INFO,
  SPATIAL_METHOD_INFO,
  linkedAsLabel,
} from "@/lib/variable-grouping";
import { datasetsForVariable } from "@/lib/data-sources";
import { CatalogDetail } from "@/components/catalog-detail";
import { DatasetDetail } from "@/components/data-sources-guide";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface OntologyNodeDetailProps {
  /** The ontology node id currently focused (null = nothing selected). */
  nodeId: string | null;
  /** Placeholder text shown when nothing is selected. */
  emptyHint?: string;
}

/**
 * Read-only detail panel for an ontology node. A node linked to an exposure
 * variable (via ontology_id) renders the full metadata card — data source,
 * spatial scale, temporal coverage, its exposome measures, and data-setup
 * links. Any other node falls back to its plain ontology definition.
 *
 * Shared by the Select Exposures wizard step and the standalone Data Catalog
 * page so both surface the identical exposome-focused view.
 */
export function OntologyNodeDetail({
  nodeId,
  emptyHint = "Select a node on the left to read its definition.",
}: OntologyNodeDetailProps) {
  const { catalog } = useVariableCatalog();
  const colMeta = useColumnMeta();
  // dataset key whose acquisition detail is shown in a dialog (null = closed).
  const [dsDialog, setDsDialog] = useState<string | null>(null);

  // Map ontology node ids -> variable keys (only variables with an ontology_id).
  const nodeIdToVarKey = useMemo(() => {
    const m: Record<string, string> = {};
    if (catalog) {
      for (const [key, v] of Object.entries(catalog.variables)) {
        if (v.ontology_id) m[v.ontology_id] = key;
      }
    }
    return m;
  }, [catalog]);

  const focusedVarKey = nodeId ? nodeIdToVarKey[nodeId] : undefined;
  const focusedVarMeta = focusedVarKey
    ? catalog?.variables[focusedVarKey]
    : null;
  const dataSetupLinks = focusedVarKey ? datasetsForVariable(focusedVarKey) : [];
  const dsDownload = dataSetupLinks.filter((l) => l.kind === "self-serve");
  const dsSupplied = dataSetupLinks.filter((l) => l.kind === "preset");
  const dsHasGeometry = dataSetupLinks.some((l) => l.role.includes("geometry"));
  const dsHasValues = dataSetupLinks.some((l) => l.role === "Exposure values");

  return (
    <>
      {focusedVarMeta ? (
        <div className="rounded-lg border bg-card p-5">
          <h3 className="text-lg font-semibold">{focusedVarMeta.label}</h3>
          <dl className="mt-3 grid grid-cols-[8rem_1fr] gap-x-3 gap-y-2 text-sm">
            <dt className="font-medium text-muted-foreground">Data Source</dt>
            <dd className="text-foreground/90">
              {focusedVarMeta.data_source ?? "—"}
            </dd>

            <dt className="font-medium text-muted-foreground">Spatial Scale</dt>
            <dd
              className="text-foreground/90"
              title={BOUNDARY_INFO[focusedVarMeta.boundary].blurb}
            >
              {BOUNDARY_INFO[focusedVarMeta.boundary].name}
              {BOUNDARY_INFO[focusedVarMeta.boundary].abbr
                ? ` (${BOUNDARY_INFO[focusedVarMeta.boundary].abbr})`
                : ""}
            </dd>

            {focusedVarMeta.spatial_method && (
              <>
                <dt className="font-medium text-muted-foreground">Linked as</dt>
                <dd
                  className="text-foreground/90"
                  title={SPATIAL_METHOD_INFO[focusedVarMeta.spatial_method].blurb}
                >
                  {linkedAsLabel(
                    focusedVarMeta.spatial_method,
                    focusedVarMeta.boundary
                  )}
                </dd>
              </>
            )}

            <dt className="font-medium text-muted-foreground">Temporal</dt>
            <dd className="text-foreground/90">
              {focusedVarMeta.temporal === "static"
                ? "Static — any study period"
                : "Time-varying"}
            </dd>

            <dt className="font-medium text-muted-foreground">Years Available</dt>
            <dd className="text-foreground/90">
              {focusedVarMeta.temporal === "static"
                ? `${focusedVarMeta.coverage_years[0]} vintage`
                : `${focusedVarMeta.coverage_years[0]}–${focusedVarMeta.coverage_years[1]}`}
            </dd>

            <dt className="font-medium text-muted-foreground">Unit</dt>
            <dd className="text-foreground/90">{focusedVarMeta.display_unit}</dd>
          </dl>

          <div className="mt-3">
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Description
            </h4>
            <p className="text-sm leading-relaxed text-foreground/90">
              {focusedVarMeta.description}
            </p>
          </div>

          <div className="mt-3">
            <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Exposomes ({focusedVarMeta.value_cols.length})
            </h4>
            <ul className="space-y-1.5">
              {focusedVarMeta.value_cols.map((col) => {
                const m = colMeta(col);
                return (
                  <li
                    key={col}
                    className="rounded-md border bg-muted/20 px-2.5 py-1.5"
                  >
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-xs font-medium">
                        {m?.label ?? col}
                      </span>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {col}
                      </span>
                    </div>
                    {m && (
                      <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
                        {m.definition}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>

          {dataSetupLinks.length > 0 && (
            <div className="mt-4 space-y-2 border-t pt-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Data setup
              </h4>
              {dsHasGeometry && dsHasValues && (
                <p className="text-[11px] leading-snug text-muted-foreground">
                  The <span className="font-medium">boundary geometry</span>{" "}
                  defines the spatial units (fixed, no years); the{" "}
                  <span className="font-medium">values</span> dataset carries the
                  yearly exposure. The pipeline joins them by geoid.
                </p>
              )}
              {dsDownload.length > 0 && (
                <div>
                  <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70">
                    To download
                  </p>
                  <ul className="space-y-0.5">
                    {dsDownload.map((ds) => (
                      <li key={ds.key}>
                        <button
                          type="button"
                          onClick={() => setDsDialog(ds.key)}
                          className="inline-flex items-center gap-1.5 text-left text-xs text-muted-foreground hover:text-foreground"
                        >
                          <ExternalLink className="size-3 shrink-0" />
                          <span className="hover:underline">{ds.name}</span>
                          <span className="shrink-0 rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
                            {ds.role}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {dsSupplied.length > 0 && (
                <div>
                  <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70">
                    Supplied by deployer
                  </p>
                  <ul className="space-y-0.5">
                    {dsSupplied.map((ds) => (
                      <li key={ds.key}>
                        <button
                          type="button"
                          onClick={() => setDsDialog(ds.key)}
                          className="inline-flex items-center gap-1.5 text-left text-xs text-muted-foreground hover:text-foreground"
                        >
                          <ExternalLink className="size-3 shrink-0" />
                          <span className="hover:underline">{ds.name}</span>
                          <span className="shrink-0 rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
                            {ds.role}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      ) : nodeId ? (
        <CatalogDetail selectedId={nodeId} />
      ) : (
        <div className="flex h-full min-h-[20rem] items-center justify-center rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          {emptyHint}
        </div>
      )}

      <Dialog
        open={!!dsDialog}
        onOpenChange={(open) => !open && setDsDialog(null)}
      >
        <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Data setup</DialogTitle>
            <DialogDescription>
              How to obtain this dataset and where to place it on the server.
            </DialogDescription>
          </DialogHeader>
          {dsDialog && <DatasetDetail datasetKey={dsDialog} />}
        </DialogContent>
      </Dialog>
    </>
  );
}
