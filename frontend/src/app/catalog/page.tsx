"use client";

import { useState } from "react";
import { OntologySearch } from "@/components/ontology-search";
import { OntologyTree } from "@/components/ontology-tree";
import { CatalogDetail } from "@/components/catalog-detail";

export default function CatalogPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto max-w-7xl px-6 py-8">
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            Data Catalog
          </h1>
          <p className="mt-2 text-muted-foreground">
            Browse the SPACESCANS ontology
          </p>
        </div>
      </header>

      {/* Two-panel layout */}
      <div className="mx-auto max-w-7xl px-6 py-8">
        <div className="flex gap-8">
          {/* Left panel: Search + Tree (40%) */}
          <div className="w-2/5 shrink-0 space-y-4">
            <OntologySearch onSelect={setSelectedId} />
            <div className="max-h-[calc(100vh-20rem)] overflow-y-auto rounded-lg border border-border bg-background p-3">
              <OntologyTree
                selectable={false}
                onNodeClick={setSelectedId}
              />
            </div>
          </div>

          {/* Right panel: Detail (60%) */}
          <div className="min-w-0 flex-1">
            <CatalogDetail selectedId={selectedId} />
          </div>
        </div>
      </div>
    </div>
  );
}
