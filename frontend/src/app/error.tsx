"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface the error for debugging; the boundary keeps the app usable.
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-6 text-center">
      <AlertTriangle className="size-10 text-red-500" />
      <h1 className="text-2xl font-bold tracking-tight text-foreground">
        Something went wrong
      </h1>
      <p className="max-w-md text-sm text-muted-foreground">
        An unexpected error occurred. You can try again, or head back to the
        dashboard.
      </p>
      {error?.message && (
        <pre className="max-w-md overflow-x-auto rounded-md bg-muted px-3 py-2 text-left text-xs text-muted-foreground">
          {error.message}
        </pre>
      )}
      <div className="mt-2 flex gap-3">
        <button
          onClick={reset}
          className="inline-flex items-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/80"
        >
          Try again
        </button>
        <Link
          href="/dashboard"
          className="inline-flex items-center rounded-lg border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}
