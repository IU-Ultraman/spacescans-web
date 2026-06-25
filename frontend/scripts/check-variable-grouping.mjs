// Sprint 3 T10 smoke: exercises variable-grouping helpers via the tsc-emitted JS output.
import assert from 'node:assert/strict';
import {
  groupByBoundary,
  groupByExperiment,
  groupByDomain,
  BOUNDARY_ORDER,
  BOUNDARY_LABEL,
  DOMAIN_ORDER,
  VARIABLE_DOMAIN,
} from '../.next-check/lib/variable-grouping.js';

const catalog = {
  schema_version: 1,
  variables: {
    bg_ndi: {
      label: 'NDI', description: '', boundary: 'BG',
      coverage_years: [2013, 2020], coverage_region: 'CONUS',
      experiment: 'bg_ndi_wi', variable_type: 'continuous',
      display_unit: 'z-score', value_cols: ['ndi'],
    },
    bg_wi: {
      label: 'Walk Index', description: '', boundary: 'BG',
      coverage_years: [2014, 2019], coverage_region: 'CONUS',
      experiment: 'bg_ndi_wi', variable_type: 'continuous',
      display_unit: 'index', value_cols: ['wi'],
    },
    zcta5_cbp_food: {
      label: 'Food Retail Density', description: '', boundary: 'ZCTA5',
      coverage_years: [2013, 2020], coverage_region: 'CONUS',
      experiment: 'zcta5_cbp', variable_type: 'continuous',
      display_unit: 'per 1k', value_cols: ['food'],
    },
  },
};

const grouped = groupByBoundary(catalog.variables);
assert.deepEqual(Object.keys(grouped), ['BG', 'ZCTA5']);
assert.equal(grouped.BG.length, 2);
assert.equal(grouped.BG[0][0], 'bg_ndi');
assert.equal(grouped.ZCTA5[0][0], 'zcta5_cbp_food');
assert.equal(grouped.Tract, undefined);

const byExp = groupByExperiment(['zcta5_cbp_food', 'bg_ndi', 'bg_wi'], catalog);
assert.deepEqual(Object.keys(byExp), ['bg_ndi_wi', 'zcta5_cbp']);
assert.deepEqual(byExp.bg_ndi_wi, ['bg_ndi', 'bg_wi']);

assert.deepEqual([...BOUNDARY_ORDER], ['BG', 'Tract', 'ZCTA5', 'County']);
assert.equal(BOUNDARY_LABEL.BG, 'Block Group');

// --- domain grouping ---
// The 9 real variables must each map to the expected environmental domain.
const EXPECTED_DOMAIN = {
  walkability: 'built', tiger_proximity: 'built', fara_tract: 'built',
  noise: 'natural', vnl: 'natural', temis: 'natural', nhd_bluespace: 'natural',
  ndi: 'social', cbp_zcta5: 'social',
};
for (const [k, d] of Object.entries(EXPECTED_DOMAIN)) {
  assert.equal(VARIABLE_DOMAIN[k], d, `VARIABLE_DOMAIN[${k}] should be ${d}`);
}
assert.deepEqual([...DOMAIN_ORDER], ['built', 'natural', 'social']);

// groupByDomain returns groups in DOMAIN_ORDER; an unknown key lands in 'other'.
const domainCatalog = {
  schema_version: 1,
  variables: {
    noise: { ...catalog.variables.bg_ndi, label: 'Noise' },         // natural
    ndi: { ...catalog.variables.bg_ndi, label: 'NDI' },             // social
    walkability: { ...catalog.variables.bg_wi, label: 'Walk' },     // built
    mystery_var: { ...catalog.variables.bg_wi, label: 'Mystery' },  // unmapped
  },
};
const byDomain = groupByDomain(domainCatalog.variables);
assert.deepEqual(Object.keys(byDomain), ['built', 'natural', 'social', 'other']);
assert.equal(byDomain.built[0][0], 'walkability');
assert.equal(byDomain.natural[0][0], 'noise');
assert.equal(byDomain.social[0][0], 'ndi');
assert.equal(byDomain.other[0][0], 'mystery_var');

console.log('variable-grouping smoke OK');
