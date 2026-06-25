"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { useVariableCatalog } from "@/lib/use-variable-catalog";
import {
  DOMAIN_ORDER, DOMAIN_GROUP_LABEL, groupByDomain,
  type DomainGroupKey,
} from "@/lib/variable-grouping";
import { ErrorCard } from "./error-card";
import { LoadingCard } from "./loading-card";
import { SchemaMismatchBanner } from "./schema-mismatch-banner";
import { VariableCard } from "./variable-card";

const EXPECTED_VARIABLE_SCHEMA_VERSION = 1;

// Domain groups rendered in order, with any unmapped variables last.
const GROUP_ORDER: DomainGroupKey[] = [...DOMAIN_ORDER, "other"];

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

  useEffect(() => {
    if (!catalog) return;
    const known = new Set(Object.keys(catalog.variables));
    setSelected((prev) => prev.filter((k) => known.has(k)));
  }, [catalog]);

  const grouped = useMemo(
    () => (catalog ? groupByDomain(catalog.variables) : null),
    [catalog],
  );

  if (loadError) return <ErrorCard message={loadError} />;
  if (!catalog || !grouped) {
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

  const toggleSelection = (key: string) =>
    setSelected((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );

  const canContinue = selected.length >= 1;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Select Exposures</CardTitle>
        <CardDescription>
          Browse the exposures you can link, grouped by environmental domain.
          Pick one or more, then upload your cohort. Click &ldquo;View in
          ontology&rdquo; on any card for its formal definition.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {GROUP_ORDER.map((group) => {
          const entries = grouped[group];
          if (!entries || entries.length === 0) return null;
          return (
            <section key={group} className="space-y-3">
              <h3 className="text-sm font-medium text-muted-foreground">
                {DOMAIN_GROUP_LABEL[group]}
              </h3>
              <div className="space-y-3">
                {entries.map(([key, meta]) => (
                  <VariableCard
                    key={key}
                    varKey={key}
                    meta={meta}
                    checked={selected.includes(key)}
                    onToggle={() => toggleSelection(key)}
                  />
                ))}
              </div>
            </section>
          );
        })}

        <div className="flex justify-between pt-4">
          {onBack ? (
            <Button variant="outline" onClick={onBack} size="lg">
              <ArrowLeft className="size-4" /> Back
            </Button>
          ) : (
            <span />
          )}
          <Button
            onClick={() => onComplete(selected)}
            disabled={!canContinue}
            size="lg"
          >
            Next <ArrowRight className="size-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
