import { DataSourcesGuide } from "@/components/data-sources-guide";

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

      <DataSourcesGuide />
    </div>
  );
}
