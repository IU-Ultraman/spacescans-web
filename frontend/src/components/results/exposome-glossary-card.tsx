"use client";

import Link from "next/link";
import { BookOpen, ExternalLink } from "lucide-react";
import { useVariableCatalog } from "@/lib/use-variable-catalog";
import { useColumnMeta } from "@/lib/use-column-meta";

interface ExposomeGlossaryCardProps {
  /** Variable keys computed for this task (task.variables). */
  variableKeys: string[];
}

/**
 * Results-page glossary: for each exposure variable in the task, show a plain-
 * language definition, the measures (value_cols) it produced, and a deep-link
 * to its full Data Catalog entry. Placed above the result tables so users can
 * recall what each exposome means before reading the numbers — the column
 * tooltips alone are hover-only and easy to miss.
 */
export function ExposomeGlossaryCard({
  variableKeys,
}: ExposomeGlossaryCardProps) {
  const { catalog } = useVariableCatalog();
  const colMeta = useColumnMeta();

  // Keep only the variables we have catalog metadata for; skip unknown keys
  // (e.g. a legacy task referencing a since-removed variable) rather than crash.
  const entries = variableKeys.flatMap((key) => {
    const meta = catalog?.variables[key];
    return meta ? [{ key, meta }] : [];
  });

  if (entries.length === 0) return null;

  return (
    <div className="rounded-lg border bg-card p-6 shadow-sm">
      <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <BookOpen className="size-4" />
        What these exposomes mean
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Plain-language definitions for the {entries.length} exposure
        {entries.length === 1 ? "" : "s"} in this result. Open the ontology for
        the full definition, provenance, and related concepts.
      </p>
      <div className="mt-4 space-y-3">
        {entries.map(({ key, meta }) => (
          <div key={key} className="rounded-md border bg-muted/20 p-4">
            <div className="flex items-start justify-between gap-3">
              <h3 className="text-sm font-semibold text-foreground">
                {meta.label}
              </h3>
              {meta.ontology_id && (
                <Link
                  href={`/catalog?node=${encodeURIComponent(meta.ontology_id)}`}
                  className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary hover:underline"
                >
                  View in ontology
                  <ExternalLink className="size-3" />
                </Link>
              )}
            </div>
            {meta.description && (
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                {meta.description}
              </p>
            )}
            {meta.value_cols.length > 0 && (
              <ul className="mt-2.5 space-y-1.5">
                {meta.value_cols.map((col) => {
                  const m = colMeta(col);
                  return (
                    <li
                      key={col}
                      className="flex flex-wrap items-baseline gap-x-1.5"
                    >
                      <span className="text-xs font-medium text-foreground/90">
                        {m?.label ?? col}
                      </span>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {col}
                      </span>
                      {m?.definition && (
                        <span className="w-full text-[11px] leading-snug text-muted-foreground">
                          {m.definition}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
