import Link from "next/link";
import { ExternalLink, Lock, Globe, FolderInput, Info } from "lucide-react";
import { Card } from "@/components/ui/card";
import { SELF_SERVE_DATASETS, PRESET_DATASETS } from "@/lib/data-sources";

export default function DataSetupPage() {
  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Data Setup
        </h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          The pipeline links your cohort against these server-side exposure
          datasets. They are <span className="font-medium">not</span> uploaded
          here — a deployer places them under{" "}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">
            SPACESCANS_DATA_DIR
          </code>{" "}
          (the repo&apos;s{" "}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">data_full/</code>).
          Most are US federal public-domain data you can fetch directly; a few
          are preprocessed and supplied by the deployer.
        </p>
      </header>

      {/* Self-serve public datasets */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Self-serve datasets ({SELF_SERVE_DATASETS.length})
        </h2>
        <div className="grid gap-4">
          {SELF_SERVE_DATASETS.map((d) => (
            <Card key={d.key} className="space-y-4 p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="font-semibold text-foreground">{d.name}</h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Used by: {d.usedBy}
                  </p>
                </div>
                <span
                  className={
                    "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium " +
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
                      <code className="rounded bg-muted px-1 py-0.5">
                        {f.name}
                      </code>
                      {f.note && (
                        <span className="ml-1.5 text-muted-foreground">
                          — {f.note}
                        </span>
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
                  <li
                    key={i}
                    className="flex gap-1.5 text-xs text-muted-foreground"
                  >
                    <Info className="mt-0.5 size-3 shrink-0" />
                    <span>{n}</span>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      </section>

      {/* Preprocessed derivatives */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Preprocessed datasets — supplied by the deployer
        </h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          These are derived artifacts (<code className="rounded bg-muted px-1 py-0.5 text-xs">.rds</code>/
          <code className="rounded bg-muted px-1 py-0.5 text-xs">.Rda</code>) built from
          public sources by the project/collaborator — they can&apos;t be
          downloaded from an official site, so the deployer provides them.
          Self-serve steps are out of scope for now.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {PRESET_DATASETS.map((d) => (
            <Card key={d.name} className="space-y-1 p-4">
              <h3 className="text-sm font-semibold text-foreground">{d.name}</h3>
              <p className="text-xs">
                <code className="rounded bg-muted px-1 py-0.5">{d.artifact}</code>
              </p>
              <p className="text-xs text-muted-foreground">{d.origin}</p>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
