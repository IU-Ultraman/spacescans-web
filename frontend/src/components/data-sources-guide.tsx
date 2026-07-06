import { ExternalLink, Lock, Globe, FolderInput, Info } from "lucide-react";
import { Card } from "@/components/ui/card";
import {
  SELF_SERVE_DATASETS,
  PRESET_DATASETS,
  type SelfServeDataset,
  type PresetDataset,
} from "@/lib/data-sources";

/** Full acquisition card for one self-serve public dataset. */
export function SelfServeCard({ d }: { d: SelfServeDataset }) {
  return (
    <Card id={d.key} className="scroll-mt-20 space-y-4 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-semibold text-foreground">{d.name}</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Used by: {d.usedBy}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
            {d.role}
          </span>
          <span
            className={
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium " +
              (d.access === "public"
                ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                : "border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-400")
            }
          >
            {d.access === "public" ? (
              <>
                <Globe className="size-3" /> Public
              </>
            ) : (
              <>
                <Lock className="size-3" /> Free account
              </>
            )}
          </span>
        </div>
      </div>

      <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-[auto_1fr]">
        <dt className="font-medium text-muted-foreground">Source</dt>
        <dd>
          <a
            href={d.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-foreground hover:underline"
          >
            {d.sourceName}
            <ExternalLink className="size-3 shrink-0" />
          </a>
        </dd>
        <dt className="font-medium text-muted-foreground">License</dt>
        <dd className="text-muted-foreground">{d.license}</dd>
        <dt className="font-medium text-muted-foreground">Size</dt>
        <dd className="text-muted-foreground">{d.size}</dd>
      </dl>

      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground">
          Files to download
        </p>
        <ul className="space-y-0.5">
          {d.files.map((f) => (
            <li key={f.name} className="text-xs">
              <code className="rounded bg-muted px-1 py-0.5">{f.name}</code>
              {f.note && (
                <span className="ml-1.5 text-muted-foreground">— {f.note}</span>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-1">
        <p className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
          <FolderInput className="size-3.5" /> Place in
        </p>
        <ul className="space-y-0.5">
          {d.placeDir.map((p) => (
            <li key={p}>
              <code className="break-all rounded bg-muted px-1 py-0.5 text-xs text-foreground">
                {p}
              </code>
            </li>
          ))}
        </ul>
      </div>

      <ul className="space-y-1 border-t pt-3">
        {d.notes.map((n, i) => (
          <li key={i} className="flex gap-1.5 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3 shrink-0" />
            <span>{n}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** Compact card for one preprocessed derivative (deployer-supplied). */
export function PresetCard({ d }: { d: PresetDataset }) {
  return (
    <Card id={d.key} className="scroll-mt-20 space-y-1 p-4">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">{d.name}</h3>
        <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
          {d.role}
        </span>
      </div>
      <p className="text-xs">
        <code className="rounded bg-muted px-1 py-0.5">{d.artifact}</code>
      </p>
      <p className="text-xs text-muted-foreground">{d.origin}</p>
      <p className="pt-1 text-[11px] text-muted-foreground">
        Supplied by the deployer — not downloadable from an official site.
      </p>
    </Card>
  );
}

/** One dataset's detail by key — rendered inside the Select Exposures dialog. */
export function DatasetDetail({ datasetKey }: { datasetKey: string }) {
  const ss = SELF_SERVE_DATASETS.find((d) => d.key === datasetKey);
  if (ss) return <SelfServeCard d={ss} />;
  const ps = PRESET_DATASETS.find((d) => d.key === datasetKey);
  if (ps) return <PresetCard d={ps} />;
  return <p className="text-sm text-muted-foreground">Unknown dataset.</p>;
}

/**
 * Full acquisition guide. Rendered on /dashboard/data-setup (all datasets, or a
 * single one when `only` is set). Pure presentational — works in server/client.
 */
export function DataSourcesGuide({ only }: { only?: string }) {
  const selfServe = only
    ? SELF_SERVE_DATASETS.filter((d) => d.key === only)
    : SELF_SERVE_DATASETS;
  const preset = only
    ? PRESET_DATASETS.filter((d) => d.key === only)
    : PRESET_DATASETS;
  return (
    <div className="space-y-8">
      {selfServe.length > 0 && (
        <section className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Self-serve datasets ({selfServe.length})
          </h2>
          <div className="grid gap-4">
            {selfServe.map((d) => (
              <SelfServeCard key={d.key} d={d} />
            ))}
          </div>
        </section>
      )}

      {preset.length > 0 && (
        <section className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Preprocessed datasets — supplied by the deployer
          </h2>
          <p className="max-w-3xl text-sm text-muted-foreground">
            These are derived artifacts (
            <code className="rounded bg-muted px-1 py-0.5 text-xs">.rds</code>/
            <code className="rounded bg-muted px-1 py-0.5 text-xs">.Rda</code>)
            built from public sources by the project/collaborator — they
            can&apos;t be downloaded from an official site, so the deployer
            provides them. Self-serve steps are out of scope for now.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {preset.map((d) => (
              <PresetCard key={d.key} d={d} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
