"use client";

import { ExternalLink } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Chip } from "@/components/ui/chip";
import type { VariableMetadata } from "@/lib/api";
import { VariableCoveragePanel } from "./variable-coverage-panel";

interface VariableCardProps {
  varKey: string;
  meta: VariableMetadata;
  checked: boolean;
  onToggle: () => void;
  /** When provided, a per-variable coverage panel is shown once checked.
   *  Omitted in the Select-Exposures step (no task/cohort uploaded yet). */
  taskId?: string;
}

export function VariableCard({
  varKey, meta, checked, onToggle, taskId,
}: VariableCardProps) {
  return (
    <label className="flex items-start gap-3 rounded-md border border-border p-3 hover:bg-muted/30 cursor-pointer">
      <Checkbox checked={checked} onCheckedChange={onToggle} className="mt-0.5" />
      <div className="flex-1">
        <div className="font-medium">{meta.label}</div>
        <div className="text-sm text-muted-foreground">{meta.description}</div>
        <div className="flex gap-1 mt-1">
          <Chip>{meta.display_unit}</Chip>
          {meta.temporal === "static" ? (
            <Chip>Static</Chip>
          ) : (
            <Chip>{meta.coverage_years[0]}–{meta.coverage_years[1]}</Chip>
          )}
          <Chip variant="outline">{meta.boundary}</Chip>
        </div>
        {meta.ontology_id && (
          <a
            href={`/catalog?node=${encodeURIComponent(meta.ontology_id)}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="mt-1.5 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
          >
            <ExternalLink className="size-3" />
            View in ontology
          </a>
        )}
        {checked && taskId && (
          <VariableCoveragePanel taskId={taskId} variableKey={varKey} />
        )}
      </div>
    </label>
  );
}
