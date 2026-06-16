import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface SchemaMismatchBannerProps {
  expected: number;
  actual: number;
  onRefresh: () => void;
  className?: string;
}

function SchemaMismatchBanner({
  expected, actual, onRefresh, className,
}: SchemaMismatchBannerProps) {
  return (
    <Card
      data-slot="schema-mismatch-banner"
      className={cn("border-destructive/40 bg-destructive/5", className)}
      role="alert"
    >
      <CardHeader>
        <CardTitle className="text-destructive">Catalog out of date</CardTitle>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-3 text-sm text-destructive">
        <span>
          UI knows schema_version {expected}; server reported {actual}. Please refresh.
        </span>
        <Button variant="outline" size="sm" onClick={onRefresh}>Refresh</Button>
      </CardContent>
    </Card>
  );
}

export { SchemaMismatchBanner };
export type { SchemaMismatchBannerProps };
