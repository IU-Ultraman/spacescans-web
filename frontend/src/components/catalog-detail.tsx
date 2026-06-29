"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Loader2 } from "lucide-react";

interface MetadataEntry {
  id: string;
  label: string;
  definition: string;
  [key: string]: string;
}

type MetadataMap = Record<string, MetadataEntry>;

interface CatalogDetailProps {
  selectedId: string | null;
}

let metadataCache: MetadataMap | null = null;
let metadataPromise: Promise<MetadataMap> | null = null;

function fetchMetadata(): Promise<MetadataMap> {
  if (metadataCache) return Promise.resolve(metadataCache);
  if (metadataPromise) return metadataPromise;
  metadataPromise = fetch("/ontology/metadata.json")
    .then((r) => r.json())
    .then((data: MetadataMap) => {
      metadataCache = data;
      return data;
    });
  return metadataPromise;
}

const KNOWN_FIELDS = new Set(["id", "label", "definition"]);

export function CatalogDetail({ selectedId }: CatalogDetailProps) {
  const [metadata, setMetadata] = useState<MetadataMap | null>(metadataCache);
  const [loading, setLoading] = useState(!metadataCache);

  useEffect(() => {
    if (metadataCache) {
      setMetadata(metadataCache);
      setLoading(false);
      return;
    }
    fetchMetadata()
      .then((data) => setMetadata(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-16">
          <Loader2 className="mr-2 size-5 animate-spin text-muted-foreground" />
          <span className="text-muted-foreground">Loading metadata...</span>
        </CardContent>
      </Card>
    );
  }

  if (!selectedId) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-16">
          <p className="text-muted-foreground">
            Select a class to view details
          </p>
        </CardContent>
      </Card>
    );
  }

  const entry = metadata?.[selectedId];

  if (!entry) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-16">
          <p className="text-muted-foreground">
            No metadata found for <span className="font-mono">{selectedId}</span>
          </p>
        </CardContent>
      </Card>
    );
  }

  const extraFields = Object.entries(entry).filter(
    ([key]) => !KNOWN_FIELDS.has(key)
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">
          {entry.label.replace(/_/g, " ")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {entry.definition && (
          <div>
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Definition
            </h4>
            <p className="text-sm leading-relaxed text-foreground/90">
              {entry.definition}
            </p>
          </div>
        )}
        {extraFields.map(([key, value]) => (
          <div key={key}>
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {key.replace(/_/g, " ")}
            </h4>
            <p className="text-sm leading-relaxed text-foreground/90">
              {value}
            </p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
