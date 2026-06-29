"use client";

import { useEffect, useState } from "react";

/**
 * Look up a human label + definition for a result.csv exposure column from the
 * SPACESCANS ontology. The value_col ontology nodes are keyed `SPACESCANS_VC_<col>`
 * (see backend/scripts/extend_ontology.py), so a raw column name maps directly.
 * Input columns (pid, startDate, geoids, …) have no node and resolve to null.
 */
interface OntoEntry {
  id: string;
  label: string;
  definition: string;
}
type OntoMap = Record<string, OntoEntry>;

let cache: OntoMap | null = null;
let inflight: Promise<OntoMap> | null = null;

function loadOntologyMetadata(): Promise<OntoMap> {
  if (cache) return Promise.resolve(cache);
  if (!inflight) {
    inflight = fetch("/ontology/metadata.json")
      .then((r) => r.json())
      .then((d: OntoMap) => {
        cache = d;
        return d;
      });
  }
  return inflight;
}

export interface ColumnMeta {
  label: string;
  definition: string;
}

/**
 * Returns a lookup `(col) => ColumnMeta | null`. Re-renders once the ontology
 * metadata has loaded. Fails silently (returns null for every column) if the
 * metadata can't be fetched, so call sites just fall back to the raw name.
 */
export function useColumnMeta(): (col: string) => ColumnMeta | null {
  const [map, setMap] = useState<OntoMap | null>(cache);

  useEffect(() => {
    if (cache) return;
    let cancelled = false;
    loadOntologyMetadata()
      .then((d) => {
        if (!cancelled) setMap(d);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  return (col: string): ColumnMeta | null => {
    const entry = map?.[`SPACESCANS_VC_${col}`];
    return entry ? { label: entry.label, definition: entry.definition } : null;
  };
}
