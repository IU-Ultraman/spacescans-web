"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { useVariableCatalog } from "@/lib/use-variable-catalog";
import { OntologyTree } from "@/components/ontology-tree";
import { OntologyNodeDetail } from "@/components/ontology/ontology-node-detail";
import { EXPOSOME_ROOT } from "@/lib/ontology";
import { ErrorCard } from "./error-card";
import { LoadingCard } from "./loading-card";
import { SchemaMismatchBanner } from "./schema-mismatch-banner";

const EXPECTED_VARIABLE_SCHEMA_VERSION = 1;

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

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Data Catalog</CardTitle>
        <CardDescription>
          Browse the Spatial &amp; Contextual Exposome ontology. Expand a branch
          to see its exposures and their exposomes; check an exposure to compute
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

          {/* Right: detail — shared read-only ontology node panel. */}
          <div className="min-w-0 flex-1">
            <OntologyNodeDetail
              nodeId={focusedNodeId}
              emptyHint="Select a node on the left to read its definition. Checkboxes mark the exposures you can compute."
            />
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
