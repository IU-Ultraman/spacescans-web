import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { DataSourcesGuide } from "@/components/data-sources-guide";
import { SELF_SERVE_DATASETS, PRESET_DATASETS } from "@/lib/data-sources";

export default function DataSetupPage({
  searchParams,
}: {
  searchParams?: { dataset?: string };
}) {
  const only = searchParams?.dataset;
  const focus = only
    ? [...SELF_SERVE_DATASETS, ...PRESET_DATASETS].find((d) => d.key === only)
    : undefined;

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        {focus ? (
          <>
            <Link
              href="/dashboard/data-setup"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
            >
              <ArrowLeft className="size-3" /> All datasets
            </Link>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Data Setup — {focus.name}
            </h1>
            <p className="max-w-3xl text-sm text-muted-foreground">
              How to obtain this dataset and where to place it under{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                SPACESCANS_DATA_DIR
              </code>{" "}
              (the repo&apos;s{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                data_full/
              </code>
              ).
            </p>
          </>
        ) : (
          <>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Data Setup
            </h1>
            <p className="max-w-3xl text-sm text-muted-foreground">
              The pipeline links your cohort against these server-side exposure
              datasets. They are <span className="font-medium">not</span>{" "}
              uploaded here — a deployer places them under{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                SPACESCANS_DATA_DIR
              </code>{" "}
              (the repo&apos;s{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                data_full/
              </code>
              ). Most are US federal public-domain data you can fetch directly;
              a few are preprocessed and supplied by the deployer.
            </p>
          </>
        )}
      </header>

      <DataSourcesGuide only={only} />

      {only && !focus && (
        <p className="text-sm text-muted-foreground">
          Unknown dataset “{only}”.{" "}
          <Link
            href="/dashboard/data-setup"
            className="text-foreground hover:underline"
          >
            View all datasets
          </Link>
          .
        </p>
      )}
    </div>
  );
}
