"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { useVariableCatalog } from "@/lib/use-variable-catalog";
import { BOUNDARY_INFO } from "@/lib/variable-grouping";
import { useColumnMeta } from "@/lib/use-column-meta";
import { OntologyTree } from "@/components/ontology-tree";
import { CatalogDetail } from "@/components/catalog-detail";
import { ErrorCard } from "./error-card";
import { LoadingCard } from "./loading-card";
import { SchemaMismatchBanner } from "./schema-mismatch-banner";

const EXPECTED_VARIABLE_SCHEMA_VERSION = 1;
// Root of the exposure taxonomy — the tree is scoped to this subtree so the
// user browses only Spatial & Contextual Exposome (not Person/Time/etc.).
const EXPOSOME_ROOT = "000093_2";

interface VariablesStepProps {
  onComplete: (selectedVariables: string[]) => void;
  /** Optional — the first wizard step has no "Back" target. */
  onBack?: () => void;
  initialSelection?: string[];
}

export function VariablesStep({
  onComplete, onBack, initialSelection = [],
}: VariablesStepProps) {
  const { catalog, error: loadError } = useVariableCatalog();
  const colMeta = useColumnMeta();
  const [selected, setSelected] = useState<string[]>(initialSelection);
  // ontology node id currently shown in the right-hand detail panel.
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);

  // Map between ontology node ids and variable keys (only variables with an
  // ontology_id are selectable in the tree).
  const nodeIdToVarKey = useMemo(() => {
    const m: Record<string, string> = {};
    if (catalog) {
      for (const [key, v] of Object.entries(catalog.variables)) {
        if (v.ontology_id) m[v.ontology_id] = key;
      }
    }
    return m;
  }, [catalog]);

  const selectableIds = useMemo(
    () => Object.keys(nodeIdToVarKey),
    [nodeIdToVarKey],
  );

  useEffect(() => {
    if (!catalog) return;
    const known = new Set(Object.keys(catalog.variables));
    setSelected((prev) => prev.filter((k) => known.has(k)));
  }, [catalog]);

  if (loadError) return <ErrorCard message={loadError} />;
  if (!catalog) {
    return <LoadingCard message="Loading exposure catalog..." />;
  }
  if (catalog.schema_version !== EXPECTED_VARIABLE_SCHEMA_VERSION) {
    return (
      <SchemaMismatchBanner
        expected={EXPECTED_VARIABLE_SCHEMA_VERSION}
        actual={catalog.schema_version}
        onRefresh={() => window.location.reload()}
      />
    );
  }

  const canContinue = selected.length >= 1;

  // Selected variable keys -> their ontology node ids (for the tree's checkboxes).
  const selectedNodeIds = selected
    .map((k) => catalog.variables[k]?.ontology_id)
    .filter((id): id is string => Boolean(id));

  const focusedVarKey = focusedNodeId ? nodeIdToVarKey[focusedNodeId] : undefined;
  const focusedVarMeta = focusedVarKey ? catalog.variables[focusedVarKey] : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Data Catalog</CardTitle>
        <CardDescription>
          Browse the Spatial &amp; Contextual Exposome ontology. Expand a branch
          to see its exposures and their outcomes; check an exposure to compute
          it for your cohort. Click any node to read its definition.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-5 md:min-h-[32rem] md:flex-row">
          {/* Left: scoped, selectable ontology tree */}
          <div className="md:w-2/5 md:shrink-0">
            <div className="max-h-[32rem] overflow-y-auto rounded-lg border p-2">
              <OntologyTree
                rootId={EXPOSOME_ROOT}
                selectable
                selectableIds={selectableIds}
                selected={selectedNodeIds}
                onSelectionChange={(ids) =>
                  setSelected(
                    ids
                      .map((id) => nodeIdToVarKey[id])
                      .filter((k): k is string => Boolean(k)),
                  )
                }
                onNodeClick={setFocusedNodeId}
              />
            </div>
          </div>

          {/* Right: detail. Variable nodes show the full metadata card;
              other nodes (domains, outcomes) show their ontology definition. */}
          <div className="min-w-0 flex-1">
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
                    {BOUNDARY_INFO[focusedVarMeta.boundary].name} (
                    {focusedVarMeta.boundary})
                  </dd>

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
                    Outcomes ({focusedVarMeta.value_cols.length})
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
              </div>
            ) : focusedNodeId ? (
              <CatalogDetail selectedId={focusedNodeId} />
            ) : (
              <div className="flex h-full min-h-[20rem] items-center justify-center rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                Select a node on the left to read its definition. Checkboxes mark
                the exposures you can compute.
              </div>
            )}
          </div>
        </div>

        <div className="mt-6 flex items-center justify-between">
          {onBack ? (
            <Button variant="outline" onClick={onBack} size="lg">
              <ArrowLeft className="size-4" /> Back
            </Button>
          ) : (
            <span />
          )}
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground">
              {selected.length} selected
            </span>
            <Button
              onClick={() => onComplete(selected)}
              disabled={!canContinue}
              size="lg"
            >
              Next <ArrowRight className="size-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
