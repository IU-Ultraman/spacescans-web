"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useOntologyNode } from "@/lib/use-column-meta";
import {
  KIND_INFO,
  TEMPORAL_LABEL,
  boundaryLabel,
  matchingNote,
  temporalHint,
  type DatasetKey,
  type RegisteredDataset,
} from "@/lib/datasets";
import { DatasetBadges } from "./dataset-badges";

function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

/** An ontology concept: its label (spaces for underscores), linked to its node
 *  in the Data Catalog; the bare id until the ontology metadata has loaded. */
function ConceptLink({ id, label }: { id: string; label: string | null }) {
  return (
    <Link
      href={`/catalog?node=${encodeURIComponent(id)}`}
      className="text-primary hover:underline"
      title={`Ontology node ${id}`}
    >
      {label ? label.replace(/_/g, " ") : id}
    </Link>
  );
}

/**
 * Everything known about one registered dataset. The list endpoint returns a
 * summary; the full record (source, version, terms, key, files) is fetched
 * here, and the summary is shown meanwhile.
 */
export function DatasetDetail({
  dataset,
  actions,
}: {
  dataset: RegisteredDataset;
  /** Owner controls rendered under the heading (edit, share, delete). */
  actions?: React.ReactNode;
}) {
  const [full, setFull] = useState<RegisteredDataset | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const ontologyNode = useOntologyNode();

  useEffect(() => {
    let cancelled = false;
    setFull(null);
    setError(null);
    setLoading(true);
    api
      .getDataset(dataset.id)
      .then((d) => !cancelled && setFull(d))
      .catch((e) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "Could not load the details");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [dataset.id]);

  // The summary wins for what it carries (it may be newer, e.g. right after a
  // share toggle); the full record fills in the rest.
  const d: RegisteredDataset = { ...(full ?? {}), ...dataset } as RegisteredDataset;
  for (const k of ["source", "version", "description", "license_note", "ontology_id", "key", "files", "checksum", "spacescans_version"] as const) {
    if (d[k] == null && full?.[k] != null) (d as unknown as Record<string, unknown>)[k] = full[k];
  }
  const kind = KIND_INFO[d.kind];
  const key: DatasetKey | null = d.key && typeof d.key === "object" ? d.key : null;

  const concept = (id: string) => <ConceptLink id={id} label={ontologyNode(id)?.label ?? null} />;

  const rows: [string, React.ReactNode | null][] = [
    ["Kind", kind?.label ?? d.kind],
    ["Ontology concept", d.ontology_id ? concept(d.ontology_id) : null],
    ["Linked as", kind?.linkedAs ?? null],
    [
      "Areas",
      d.kind === "polygon_table" && key?.geography
        ? `${boundaryLabel(key.geography)}${key.column ? ` (codes in “${key.column}”)` : ""}`
        : null,
    ],
    [
      "Time",
      `${TEMPORAL_LABEL[d.temporal] ?? d.temporal} — ${
        key?.time_column
          ? `${d.temporal === "daily" ? "dates" : "years"} in “${key.time_column}”`
          : temporalHint(d.kind, d.temporal)
      }`,
    ],
    ["Key", typeof d.key === "string" ? d.key : null],
    ["Source", d.source ?? null],
    ["Version", d.version ?? null],
    ["Terms of use", d.license_note ?? null],
    ["Owner", d.owned_by_me ? "You" : d.owner_display || "Another user"],
    [
      "Who can use it",
      d.visibility === "deployment"
        ? "Every user of this deployment"
        : d.owned_by_me
          ? "Only you"
          : "Only its owner",
    ],
    ["Added", formatDate(d.created_at)],
    ["Files", d.files && d.files.length ? `${d.files.length} prepared file${d.files.length === 1 ? "" : "s"}` : null],
    ["Checksum", d.checksum ? `sha256 ${d.checksum.slice(0, 12)}…` : null],
    ["Prepared with", d.spacescans_version ? `spacescans ${d.spacescans_version}` : null],
  ];

  return (
    <div className="rounded-lg border p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="break-words text-xl font-semibold">{d.name}</h2>
          <DatasetBadges dataset={d} showVisibility className="mt-1.5" />
        </div>
        {loading && <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />}
      </div>
      {actions && <div className="mt-4">{actions}</div>}

      <dl className="mt-4 space-y-2">
        {rows
          .filter((r): r is [string, React.ReactNode] => !!r[1])
          .map(([term, value]) => (
            <div key={term} className="grid grid-cols-[8.5rem_1fr] gap-2 text-sm">
              <dt className="text-muted-foreground">{term}</dt>
              <dd className="min-w-0 break-words">{value}</dd>
            </div>
          ))}
      </dl>
      {error && <p className="mt-2 text-xs text-muted-foreground">Details unavailable: {error}</p>}

      {d.description && (
        <>
          <h3 className="mt-5 text-xs uppercase tracking-wide text-muted-foreground">Description</h3>
          <p className="mt-1 whitespace-pre-line text-sm">{d.description}</p>
        </>
      )}

      <h3 className="mt-5 text-xs uppercase tracking-wide text-muted-foreground">
        Result columns ({d.variables.length})
      </h3>
      <div className="mt-2 space-y-2">
        {d.variables.map((v) => (
          <div key={v.name} className="rounded-md border px-3 py-2">
            <div className="flex flex-wrap items-baseline gap-2">
              <code className="text-sm font-medium">{v.name}</code>
              {v.band != null && d.kind === "raster" && (
                <span className="text-xs text-muted-foreground">band {v.band}</span>
              )}
              {v.unit && <span className="ml-auto shrink-0 text-xs text-muted-foreground">{v.unit}</span>}
            </div>
            {v.description && <p className="mt-0.5 text-xs text-muted-foreground">{v.description}</p>}
            {v.ontology_id && v.ontology_id !== d.ontology_id && (
              <p className="mt-0.5 text-xs text-muted-foreground">Concept: {concept(v.ontology_id)}</p>
            )}
          </div>
        ))}
        {d.variables.length === 0 && (
          <p className="text-xs text-muted-foreground">No result columns listed.</p>
        )}
      </div>

      <p className="mt-5 text-xs text-muted-foreground">{matchingNote(d.temporal)}</p>
    </div>
  );
}
