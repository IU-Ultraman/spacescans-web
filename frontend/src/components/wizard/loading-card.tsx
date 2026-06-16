import * as React from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface LoadingCardProps {
  message?: string;
  className?: string;
}

function LoadingCard({ message = "Loading…", className }: LoadingCardProps) {
  return (
    <Card data-slot="loading-card" className={cn("", className)} aria-busy="true">
      <CardContent className="flex items-center gap-2 text-sm text-muted-foreground">
        <span
          className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent"
          aria-hidden="true"
        />
        <span>{message}</span>
      </CardContent>
    </Card>
  );
}

export { LoadingCard };
export type { LoadingCardProps };
