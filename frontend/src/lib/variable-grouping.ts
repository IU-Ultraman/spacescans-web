import type { VariableCatalog, VariableMetadata } from './api';

// Ordered finest → coarsest: a residential Point (a buffer around the address,
// 270 m by default — finer than any Census area) precedes Block Group ⊂ Census
// Tract ⊂ County, with ZCTA5 (ZIP-code area, ~tract-to-county scale) after Tract.
export const BOUNDARY_ORDER = ['Point', 'BG', 'Tract', 'ZCTA5', 'County'] as const;
export type BoundaryKey = typeof BOUNDARY_ORDER[number];

export const BOUNDARY_LABEL: Record<BoundaryKey, string> = {
  Point: 'Residential point',
  BG: 'Block Group',
  ZCTA5: 'ZIP Code Tabulation Area',
  Tract: 'Census Tract',
  County: 'County',
};

// Plain-language explanation of each Census geography, used in tooltips and the
// Select-Exposures detail panel. "blurb" answers "what is this and why does it
// matter" for a researcher who knows cohorts but not the Census hierarchy: it
// is the geographic resolution at which the exposure is assigned to a residence.
// `abbr` is the short tag shown in parentheses after the name (e.g. "Block
// Group (BG)"). Residential Point has no Census abbreviation, so abbr is null
// and no parenthetical is shown.
export const BOUNDARY_INFO: Record<
  BoundaryKey,
  { name: string; abbr: string | null; blurb: string }
> = {
  Point: {
    name: 'Residential point',
    abbr: null,
    blurb:
      'Assigned at each residence directly, not aggregated to a Census area. A raster exposure (noise, lights, UV) is averaged within a small buffer around the address; a proximity exposure (water, roads) is the straight-line distance from the address to the nearest feature — no buffer involved. Finer and more local than a block group.',
  },
  BG: {
    name: 'Block Group',
    abbr: 'BG',
    blurb:
      'Smallest Census area (~600–3,000 people, a few city blocks). This exposure is assigned by area-weighting the block groups the buffer overlaps.',
  },
  Tract: {
    name: 'Census Tract',
    abbr: 'Tract',
    blurb:
      'Neighborhood-sized Census area (~1,200–8,000 people), made of several block groups. This exposure is assigned at tract resolution.',
  },
  ZCTA5: {
    name: 'ZIP Code Tabulation Area',
    abbr: 'ZCTA5',
    blurb:
      "The Census Bureau's approximation of a 5-digit ZIP-code area (roughly tract-to-county scale). This exposure is assigned per ZCTA.",
  },
  County: {
    name: 'County',
    abbr: 'County',
    blurb:
      'County-level area — the coarsest resolution here. This exposure is assigned per county.',
  },
};

// Plain-language "how is this exposure linked to a residence" — the C3 method.
// Complements Spatial Scale (which only says the resolution): it distinguishes
// the two point methods (grid vs proximity) that both read as "Residential
// point", and it explains whether the buffer is used.
export type SpatialMethod = 'areal' | 'grid' | 'proximity';
export const SPATIAL_METHOD_INFO: Record<
  SpatialMethod,
  { label: string; blurb: string }
> = {
  areal: {
    label: 'Area-weighted from Census areas',
    blurb:
      'The buffer around each home is overlaid on the Census areas it touches; the exposure is the area-weighted average of those areas.',
  },
  grid: {
    label: 'Sampled from a raster grid',
    blurb:
      'The exposure raster is averaged over the cells the buffer around each home covers.',
  },
  proximity: {
    label: 'Distance to the nearest feature',
    blurb:
      'The straight-line distance from the exact home address to the nearest feature (water, road). No buffer is used.',
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
