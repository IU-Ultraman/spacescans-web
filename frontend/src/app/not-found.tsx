import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-6 text-center">
      <p className="text-sm font-semibold tracking-widest text-muted-foreground">
        404
      </p>
      <h1 className="text-2xl font-bold tracking-tight text-foreground">
        Page not found
      </h1>
      <p className="max-w-md text-sm text-muted-foreground">
        The page you’re looking for doesn’t exist or may have moved.
      </p>
      <Link
        href="/dashboard"
        className="mt-2 inline-flex items-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/80"
      >
        Back to dashboard
      </Link>
    </div>
  );
}
