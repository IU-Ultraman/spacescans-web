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

// Plain-language explanation of each Census geography, used in tooltips and the
// Select-Exposures detail panel. "blurb" answers "what is this and why does it
// matter" for a researcher who knows cohorts but not the Census hierarchy: it
// is the geographic resolution at which the exposure is assigned to a residence.
export const BOUNDARY_INFO: Record<BoundaryKey, { name: string; blurb: string }> = {
  BG: {
    name: 'Block Group',
    blurb:
      'Smallest Census area (~600–3,000 people, a few city blocks). This exposure is assigned at block-group resolution — the finest, most local.',
  },
  Tract: {
    name: 'Census Tract',
    blurb:
      'Neighborhood-sized Census area (~1,200–8,000 people), made of several block groups. This exposure is assigned at tract resolution.',
  },
  ZCTA5: {
    name: 'ZIP Code Tabulation Area',
    blurb:
      "The Census Bureau's approximation of a 5-digit ZIP-code area (roughly tract-to-county scale). This exposure is assigned per ZCTA.",
  },
  County: {
    name: 'County',
    blurb:
      'County-level area — the coarsest resolution here. This exposure is assigned per county.',
  },
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

export const DOMAIN_ORDER = ['built', 'natural', 'social'] as const;
export type DomainKey = typeof DOMAIN_ORDER[number];

export const DOMAIN_LABEL: Record<DomainKey, string> = {
  built: 'Built Environment',
  natural: 'Natural Environment',
  social: 'Social Environment',
};

// Each variable's environmental domain = its linked ontology node's parent
// (Built/Natural/Social Environment Exposome). Kept as an explicit map because
// domain is a presentation concern; a new variable must be added here too.
// groupByDomain routes anything unmapped to a trailing 'other' bucket so it is
// never silently dropped, and check-variable-grouping.mjs asserts completeness.
export const VARIABLE_DOMAIN: Record<string, DomainKey> = {
  walkability: 'built',
  tiger_proximity: 'built',
  fara_tract: 'built',
  noise: 'natural',
  vnl: 'natural',
  temis: 'natural',
  nhd_bluespace: 'natural',
  ndi: 'social',
  cbp_zcta5: 'social',
};

export type DomainGroupKey = DomainKey | 'other';

export function groupByDomain(
  variables: Record<string, VariableMetadata>,
): Partial<Record<DomainGroupKey, [string, VariableMetadata][]>> {
  const out: Partial<Record<DomainGroupKey, [string, VariableMetadata][]>> = {};
  for (const d of DOMAIN_ORDER) {
    const entries = Object.entries(variables).filter(
      ([key]) => VARIABLE_DOMAIN[key] === d,
    );
    if (entries.length > 0) out[d] = entries;
  }
  const unmapped = Object.entries(variables).filter(
    ([key]) => !(key in VARIABLE_DOMAIN),
  );
  if (unmapped.length > 0) out.other = unmapped;
  return out;
}

export const DOMAIN_GROUP_LABEL: Record<DomainGroupKey, string> = {
  ...DOMAIN_LABEL,
  other: 'Other',
};

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
