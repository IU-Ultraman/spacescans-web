import * as React from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface ErrorCardProps {
  message: string;
  title?: string;
  className?: string;
}

function ErrorCard({ message, title = "Something went wrong", className }: ErrorCardProps) {
  return (
    <Card
      data-slot="error-card"
      className={cn("border-destructive/40 bg-destructive/5", className)}
      role="alert"
    >
      <CardHeader>
        <CardTitle className="text-destructive">{title}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-destructive">{message}</CardContent>
    </Card>
  );
}

export { ErrorCard };
export type { ErrorCardProps };
