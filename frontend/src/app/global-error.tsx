"use client";

// Catches errors thrown by the root layout itself. It replaces the root
// layout, so it must render its own <html>/<body>. Tailwind/theme may not be
// available here, so styling is inline and self-contained.
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          minHeight: "100vh",
          margin: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "1rem",
          padding: "1.5rem",
          textAlign: "center",
          fontFamily: "system-ui, -apple-system, sans-serif",
          background: "#ffffff",
          color: "#111827",
        }}
      >
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0 }}>
          Something went wrong
        </h1>
        <p style={{ color: "#6b7280", maxWidth: "28rem", margin: 0 }}>
          A critical error occurred while loading the app. Please reload the
          page.
        </p>
        <button
          onClick={() => reset()}
          style={{
            borderRadius: "0.5rem",
            background: "#111827",
            color: "#ffffff",
            padding: "0.5rem 1rem",
            fontSize: "0.875rem",
            border: "none",
            cursor: "pointer",
          }}
        >
          Reload
        </button>
      </body>
    </html>
  );
}
