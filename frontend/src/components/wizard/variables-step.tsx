"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { useVariableCatalog } from "@/lib/use-variable-catalog";
import type { RegisteredDataset } from "@/lib/datasets";
import { OntologyTree } from "@/components/ontology-tree";
import { OntologyNodeDetail } from "@/components/ontology/ontology-node-detail";
import { DatasetDetail } from "@/components/datasets/dataset-detail";
import { DatasetsBlock } from "./datasets-block";
import { EXPOSOME_ROOT } from "@/lib/ontology";
import { ErrorCard } from "./error-card";
import { LoadingCard } from "./loading-card";
import { SchemaMismatchBanner } from "./schema-mismatch-banner";

const EXPECTED_VARIABLE_SCHEMA_VERSION = 1;

interface VariablesStepProps {
  /** Catalog variable keys, and the registered datasets chosen next to them. */
  onComplete: (selectedVariables: string[], selectedDatasets: RegisteredDataset[]) => void;
  /** Optional — the first wizard step has no "Back" target. */
  onBack?: () => void;
  initialSelection?: string[];
  initialDatasets?: RegisteredDataset[];
}

export function VariablesStep({
  onComplete, onBack, initialSelection = [], initialDatasets = [],
}: VariablesStepProps) {
  const { catalog, error: loadError } = useVariableCatalog();
  // Catalog variable keys only; the user's datasets are selected by id.
  const [selected, setSelected] = useState<string[]>(initialSelection);
  const [selectedDatasets, setSelectedDatasets] = useState<string[]>(() =>
    initialDatasets.map((d) => d.id),
  );
  const [datasetIndex, setDatasetIndex] = useState<Record<string, RegisteredDataset>>(() =>
    Object.fromEntries(initialDatasets.map((d) => [d.id, d])),
  );
  // ontology node id currently shown in the right-hand detail panel.
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  // A registered dataset shown in that panel instead — it has no ontology
  // node, so the two are mutually exclusive: focusing one clears the other.
  const [focusedDataset, setFocusedDataset] = useState<RegisteredDataset | null>(null);

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

  const totalSelected = selected.length + selectedDatasets.length;
  const canContinue = totalSelected >= 1;

  // Selected variable keys -> their ontology node ids (for the tree's checkboxes).
  const selectedNodeIds = selected
    .map((k) => catalog.variables[k]?.ontology_id)
    .filter((id): id is string => Boolean(id));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Select Exposures</CardTitle>
        <CardDescription>
          Check the exposures to compute for your cohort — from the catalog this
          deployment provides, or from your own datasets (and those shared with
          you). Click any item to read its definition on the right.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-5 md:min-h-[32rem] md:flex-row">
          {/* Left: scoped, selectable ontology tree */}
          <div className="md:w-2/5 md:shrink-0">
            <div className="rounded-lg border">
              <div className="border-b px-3 py-2">
                <div className="text-sm font-medium">Data Catalog</div>
                <div className="truncate text-xs text-muted-foreground">
                  {selectableIds.length} exposures from the Spatial &amp;
                  Contextual Exposome ontology
                </div>
              </div>
              <div className="max-h-[28rem] overflow-y-auto p-2">
              <OntologyTree
                rootId={EXPOSOME_ROOT}
                selectable
                selectableIds={selectableIds}
                autoExpandTo={selectableIds}
                selected={selectedNodeIds}
                onSelectionChange={(ids) =>
                  setSelected(
                    ids
                      .map((id) => nodeIdToVarKey[id])
                      .filter((k): k is string => Boolean(k)),
                  )
                }
                onNodeClick={(id) => {
                  setFocusedNodeId(id);
                  setFocusedDataset(null);
                }}
              />
              </div>
            </div>
            <DatasetsBlock
              selected={selectedDatasets}
              onSelectionChange={setSelectedDatasets}
              onLoaded={(list) => {
                setDatasetIndex(Object.fromEntries(list.map((d) => [d.id, d])));
                // Keep the panel in step with a renamed or deleted dataset.
                setFocusedDataset((cur) => (cur ? list.find((d) => d.id === cur.id) ?? null : cur));
              }}
              focusedId={focusedDataset?.id ?? null}
              onFocus={(dataset) => {
                setFocusedDataset(dataset);
                if (dataset) setFocusedNodeId(null);
              }}
            />
          </div>

          {/* Right: detail — shared read-only ontology node panel. */}
          <div className="min-w-0 flex-1">
            {focusedDataset ? (
              <DatasetDetail dataset={focusedDataset} />
            ) : (
              <OntologyNodeDetail
                nodeId={focusedNodeId}
                emptyHint="Select a node on the left to read its definition. Checkboxes mark the exposures you can compute."
              />
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
              {totalSelected} selected
            </span>
            <Button
              onClick={() =>
                onComplete(
                  selected,
                  selectedDatasets
                    .map((id) => datasetIndex[id])
                    .filter((d): d is RegisteredDataset => Boolean(d)),
                )
              }
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
