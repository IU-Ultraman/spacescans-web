import type { VariableCatalog, VariableMetadata } from './api';

// Ordered smallest → largest geography: Block Group ⊂ Census Tract ⊂
// County, with ZCTA5 (ZIP-code area, ~tract-to-county scale) placed after
// Tract. Drives the Select Variables section order.
export const BOUNDARY_ORDER = ['BG', 'Tract', 'ZCTA5', 'County'] as const;
export type BoundaryKey = typeof BOUNDARY_ORDER[number];

export const BOUNDARY_LABEL: Record<BoundaryKey, string> = {
  BG: 'Block Group',
  ZCTA5: 'ZIP Code Tabulation Area',
  Tract: 'Census Tract',
  County: 'County',
};

export function groupByBoundary(
  variables: Record<string, VariableMetadata>,
): Partial<Record<BoundaryKey, [string, VariableMetadata][]>> {
  const out: Partial<Record<BoundaryKey, [string, VariableMetadata][]>> = {};
  for (const b of BOUNDARY_ORDER) {
    const entries = Object.entries(variables).filter(([, m]) => m.boundary === b);
    if (entries.length > 0) out[b] = entries;
  }
  return out;
}

export function groupByExperiment(
  selectedKeys: string[],
  catalog: VariableCatalog,
): Record<string, string[]> {
  const selected = new Set(selectedKeys);
  const out: Record<string, string[]> = {};
  for (const [key, meta] of Object.entries(catalog.variables)) {
    if (!selected.has(key)) continue;
    (out[meta.experiment] ??= []).push(key);
  }
  return out;
}
