"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { OntologyTree } from "@/components/ontology-tree";
import { OntologyNodeDetail } from "@/components/ontology/ontology-node-detail";
import { EXPOSOME_ROOT } from "@/lib/ontology";

export default function CatalogPage() {
  const router = useRouter();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Deep-link support: /catalog?node=<id> preselects that node so the detail
  // panel shows it immediately (e.g. arriving from a result's "View in
  // ontology" link). Read client-side to avoid a Suspense boundary.
  useEffect(() => {
    const node = new URLSearchParams(window.location.search).get("node");
    if (node) setSelectedId(node);
  }, []);

  // /catalog is reachable from the landing page and from a result's "View in
  // ontology" link, so return the user wherever they came from. Fall back to
  // home when opened directly (no in-app history to pop).
  const goBack = () => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
    } else {
      router.push("/");
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto max-w-7xl px-6 py-6">
          <button
            type="button"
            onClick={goBack}
            className="mb-3 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="size-4" />
            Back
          </button>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            Data Catalog
          </h1>
          <p className="mt-2 text-muted-foreground">
            Browse the Spatial &amp; Contextual Exposome ontology
          </p>
        </div>
      </header>

      {/* Two-panel layout — the same exposome tree + rich detail as the
          Select Exposures wizard step, read-only. */}
      <div className="mx-auto max-w-7xl px-6 py-8">
        <div className="flex gap-8">
          {/* Left panel: scoped Exposome tree (40%) */}
          <div className="w-2/5 shrink-0">
            <div className="max-h-[calc(100vh-16rem)] overflow-y-auto rounded-lg border border-border bg-background p-3">
              <OntologyTree
                rootId={EXPOSOME_ROOT}
                selectable={false}
                onNodeClick={setSelectedId}
              />
            </div>
          </div>

          {/* Right panel: detail (60%) */}
          <div className="min-w-0 flex-1">
            <OntologyNodeDetail nodeId={selectedId} />
          </div>
        </div>
      </div>
    </div>
  );
}
