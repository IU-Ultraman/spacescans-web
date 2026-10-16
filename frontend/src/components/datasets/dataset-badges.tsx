"use client";

import { Lock, Loader2, Users, AlertCircle } from "lucide-react";
import { Chip } from "@/components/ui/chip";
import { cn } from "@/lib/utils";
import {
  KIND_INFO,
  TEMPORAL_LABEL,
  isFailed,
  isPending,
  type RegisteredDataset,
} from "@/lib/datasets";

/** Kind and time structure, plus the status when the dataset is not usable
 *  yet, and (optionally) who can see it. */
export function DatasetBadges({
  dataset,
  showVisibility = false,
  className,
}: {
  dataset: RegisteredDataset;
  showVisibility?: boolean;
  className?: string;
}) {
  const kind = KIND_INFO[dataset.kind]?.short ?? dataset.kind;
  const temporal = TEMPORAL_LABEL[dataset.temporal] ?? dataset.temporal;
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1", className)}>
      <Chip variant="outline" className="text-[10px]">{kind}</Chip>
      <Chip className="text-[10px]">{temporal}</Chip>
      {isPending(dataset) && (
        <Chip className="gap-1 bg-amber-500/10 text-[10px] text-amber-700 dark:text-amber-400">
          <Loader2 className="size-3 animate-spin" /> Preparing
        </Chip>
      )}
      {isFailed(dataset) && (
        <Chip className="gap-1 bg-destructive/10 text-[10px] text-destructive">
          <AlertCircle className="size-3" /> Failed
        </Chip>
      )}
      {showVisibility && <VisibilityChip dataset={dataset} />}
    </span>
  );
}

export function VisibilityChip({ dataset }: { dataset: RegisteredDataset }) {
  if (dataset.visibility === "deployment") {
    return (
      <Chip
        className="gap-1 bg-sky-500/10 text-[10px] text-sky-700 dark:text-sky-300"
        title={
          dataset.owned_by_me
            ? "Every user of this deployment can find and select it"
            : `Shared by ${dataset.owner_display || "another user"}`
        }
      >
        <Users className="size-3" />
        {dataset.owned_by_me ? "Shared" : `Shared by ${dataset.owner_display || "another user"}`}
      </Chip>
    );
  }
  return (
    <Chip className="gap-1 text-[10px]" title="Only you can see and select it">
      <Lock className="size-3" /> Private
    </Chip>
  );
}
