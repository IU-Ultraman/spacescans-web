"use client";

import { useRef, useState } from "react";
import { UploadCloud, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { Card } from "@/components/ui/card";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Phase =
  | { kind: "idle" }
  | { kind: "uploading"; pct: number; name: string }
  | { kind: "extracting"; name: string }
  | { kind: "done"; name: string; message: string }
  | { kind: "error"; name: string; message: string };

/** Upload a distribution archive and let the server extract it in place.
 * The archives carry data-root-relative paths, so the server-side extraction
 * is byte-identical to `tar -xzf <archive> -C pipeline-data/`. */
export function UploadArchivePanel() {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const inputRef = useRef<HTMLInputElement>(null);

  function upload(file: File) {
    const token =
      typeof window !== "undefined" ? localStorage.getItem("token") : null;
    const xhr = new XMLHttpRequest();
    xhr.open(
      "POST",
      `${API_BASE}/api/data/upload-archive?filename=${encodeURIComponent(file.name)}`,
    );
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable)
        setPhase({
          kind: "uploading",
          pct: Math.round((e.loaded / e.total) * 100),
          name: file.name,
        });
    };
    // Upload finished -> the server verifies the checksum, then extracts.
    xhr.upload.onload = () => setPhase({ kind: "extracting", name: file.name });
    xhr.onload = () => {
      try {
        const body = JSON.parse(xhr.responseText);
        if (xhr.status === 200) {
          const msg =
            body.extracted_files != null
              ? `extracted ${body.extracted_files} files under ${(body.top_dirs || []).join(", ")}/`
              : `placed at ${body.placed}`;
          setPhase({ kind: "done", name: file.name, message: msg });
        } else {
          const d = body.detail;
          const msg =
            typeof d === "string" ? d : d?.message || d?.error || xhr.statusText;
          setPhase({ kind: "error", name: file.name, message: msg });
        }
      } catch {
        setPhase({
          kind: "error",
          name: file.name,
          message: `unexpected response (HTTP ${xhr.status})`,
        });
      }
    };
    xhr.onerror = () =>
      setPhase({
        kind: "error",
        name: file.name,
        message: "network error during upload",
      });
    setPhase({ kind: "uploading", pct: 0, name: file.name });
    xhr.send(file);
  }

  return (
    <Card className="space-y-2 border-dashed p-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={phase.kind === "uploading" || phase.kind === "extracting"}
          className="inline-flex items-center gap-2 rounded-md border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-muted disabled:opacity-50"
        >
          <UploadCloud className="size-4" />
          Upload a distribution archive
        </button>
        <p className="text-xs text-muted-foreground">
          Pick an archive you downloaded from the deployer&apos;s OneDrive folder
          — the server verifies its SHA-256 against the published checksum, then
          extracts it into{" "}
          <code className="rounded bg-muted px-1 py-0.5">pipeline-data/</code>{" "}
          for you, no terminal needed. Only the distributed artifacts are
          accepted (a corrupt or unexpected file is rejected untouched). For the
          36 GB NHD archive, the terminal command is more reliable than a browser
          upload.
        </p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".tar.gz,.tgz,.Rda,application/gzip"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload(f);
          e.target.value = "";
        }}
      />
      {phase.kind === "uploading" && (
        <div className="space-y-1">
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="size-3 animate-spin" />
            Uploading {phase.name} — {phase.pct}%
          </p>
          <div className="h-1.5 w-full overflow-hidden rounded bg-muted">
            <div
              className="h-full rounded bg-foreground/70 transition-all"
              style={{ width: `${phase.pct}%` }}
            />
          </div>
        </div>
      )}
      {phase.kind === "extracting" && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" />
          Upload complete — verifying the checksum and extracting {phase.name} on
          the server… (large archives take a few minutes; keep this tab open)
        </p>
      )}
      {phase.kind === "done" && (
        <p className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 className="size-3.5" />
          {phase.name}: {phase.message}
        </p>
      )}
      {phase.kind === "error" && (
        <p className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
          <XCircle className="size-3.5" />
          {phase.name}: {phase.message}
        </p>
      )}
    </Card>
  );
}
