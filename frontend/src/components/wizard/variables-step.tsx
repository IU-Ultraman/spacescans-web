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
  DOMAIN_ORDER, DOMAIN_GROUP_LABEL, groupByDomain, BOUNDARY_INFO,
  type DomainGroupKey,
} from "@/lib/variable-grouping";
import { CatalogDetail } from "@/components/catalog-detail";
import { useColumnMeta } from "@/lib/use-column-meta";
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
  const colMeta = useColumnMeta();
  const [selected, setSelected] = useState<string[]>(initialSelection);
  // variable key whose definition + outcomes are shown in the right-hand panel.
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
  const focusedMeta = focused ? catalog.variables[focused] ?? null : null;

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
        <div className="flex flex-col gap-5 md:min-h-[24rem] md:flex-row">
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
                      const isFocused = focused === key;
                      const nOut = meta.value_cols.length;
                      return (
                        <div
                          key={key}
                          onClick={() => setFocused(key)}
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
                          <span className="shrink-0 text-[10px] text-muted-foreground">
                            {nOut} outcome{nOut === 1 ? "" : "s"}
                          </span>
                          <span
                            className="shrink-0"
                            title={`${BOUNDARY_INFO[meta.boundary].name} — ${BOUNDARY_INFO[meta.boundary].blurb}`}
                          >
                            <Chip variant="outline">{meta.boundary}</Chip>
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </section>
              );
            })}
          </div>

          {/* Right: ontology definition + outcomes for the focused exposure.
              Outcomes are read-only here — selection stays at the variable
              level (checking the row on the left brings ALL its outcomes). */}
          <div className="min-w-0 flex-1">
            {focusedMeta ? (
              <>
                <CatalogDetail selectedId={focusedMeta.ontology_id ?? null} />
                <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
                  <span className="font-medium text-foreground/80">
                    Geographic resolution:
                  </span>{" "}
                  {BOUNDARY_INFO[focusedMeta.boundary].name} —{" "}
                  {BOUNDARY_INFO[focusedMeta.boundary].blurb}
                </p>
                <div className="mt-3">
                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Outcomes ({focusedMeta.value_cols.length})
                  </h4>
                  <ul className="space-y-1.5">
                    {focusedMeta.value_cols.map((col) => {
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
                {focusedMeta.ontology_id && (
                  <a
                    href={`/catalog?node=${encodeURIComponent(focusedMeta.ontology_id)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-3 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
                  >
                    <ExternalLink className="size-3" />
                    Open in full ontology
                  </a>
                )}
              </>
            ) : (
              <div className="flex h-full min-h-[20rem] items-center justify-center rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                Select an exposure on the left to read its definition and outcomes.
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
