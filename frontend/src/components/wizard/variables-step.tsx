"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Chip } from "@/components/ui/chip";
import { ArrowLeft, ArrowRight, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { useVariableCatalog } from "@/lib/use-variable-catalog";
import {
  DOMAIN_ORDER, DOMAIN_GROUP_LABEL, groupByDomain,
  type DomainGroupKey,
} from "@/lib/variable-grouping";
import { CatalogDetail } from "@/components/catalog-detail";
import { ErrorCard } from "./error-card";
import { LoadingCard } from "./loading-card";
import { SchemaMismatchBanner } from "./schema-mismatch-banner";

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
  // ontology_id of the row whose definition is shown in the right-hand panel.
  const [focused, setFocused] = useState<string | null>(null);

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
        <CardTitle className="text-lg">Data Catalog</CardTitle>
        <CardDescription>
          Browse the available exposures, grouped by environmental domain and
          linked to the SPACESCANS ontology. Click an exposure to read its
          definition; check the ones to compute for your cohort.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-5 md:flex-row">
          {/* Left: selectable, domain-grouped exposure list */}
          <div className="space-y-4 md:w-2/5 md:shrink-0">
            {GROUP_ORDER.map((group) => {
              const entries = grouped[group];
              if (!entries || entries.length === 0) return null;
              return (
                <section key={group} className="space-y-1">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {DOMAIN_GROUP_LABEL[group]}
                  </h3>
                  <div className="space-y-0.5">
                    {entries.map(([key, meta]) => {
                      const isSel = selected.includes(key);
                      const isFocused =
                        meta.ontology_id != null && focused === meta.ontology_id;
                      return (
                        <div
                          key={key}
                          onClick={() => setFocused(meta.ontology_id ?? null)}
                          className={cn(
                            "flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-muted/60",
                            isFocused && "bg-primary/5",
                          )}
                        >
                          <Checkbox
                            checked={isSel}
                            onCheckedChange={() => toggleSelection(key)}
                            onClick={(e) => e.stopPropagation()}
                            className="shrink-0"
                          />
                          <span className="min-w-0 flex-1 truncate text-sm text-foreground/90">
                            {meta.label}
                          </span>
                          <Chip variant="outline">{meta.boundary}</Chip>
                        </div>
                      );
                    })}
                  </div>
                </section>
              );
            })}
          </div>

          {/* Right: ontology definition for the focused exposure */}
          <div className="min-w-0 flex-1">
            {focused ? (
              <>
                <CatalogDetail selectedId={focused} />
                <a
                  href={`/catalog?node=${encodeURIComponent(focused)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
                >
                  <ExternalLink className="size-3" />
                  Open in full ontology
                </a>
              </>
            ) : (
              <div className="flex h-full min-h-[12rem] items-center justify-center rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                Select an exposure on the left to read its definition.
              </div>
            )}
          </div>
        </div>

        <div className="mt-6 flex justify-between">
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
