import * as React from "react";

import { cn } from "@/lib/utils";

type ChipVariant = "default" | "outline";

interface ChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: ChipVariant;
}

function Chip({ className, variant = "default", ...props }: ChipProps) {
  return (
    <span
      data-slot="chip"
      data-variant={variant}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        variant === "default" && "bg-muted text-muted-foreground",
        variant === "outline" && "border border-border text-foreground",
        className,
      )}
      {...props}
    />
  );
}

const Pill = Chip;

export { Chip, Pill };
export type { ChipProps, ChipVariant };
