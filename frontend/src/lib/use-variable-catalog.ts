import { useEffect, useState } from 'react';
import { api, type VariableCatalog } from './api';

let cached: VariableCatalog | null = null;
let inflight: Promise<VariableCatalog> | null = null;

function load(): Promise<VariableCatalog> {
  if (cached) return Promise.resolve(cached);
  if (!inflight) {
    inflight = api.listVariables().then((c) => {
      cached = c;
      inflight = null;
      return c;
    });
  }
  return inflight;
}

export function useVariableCatalog(): {
  catalog: VariableCatalog | null;
  error: string | null;
} {
  const [catalog, setCatalog] = useState<VariableCatalog | null>(cached);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (catalog) return;
    let cancelled = false;
    load()
      .then((c) => !cancelled && setCatalog(c))
      .catch((e) => !cancelled && setError(String(e)));
    return () => { cancelled = true; };
  }, [catalog]);

  return { catalog, error };
}

export function __resetVariableCatalogCache(): void {
  cached = null;
  inflight = null;
}
