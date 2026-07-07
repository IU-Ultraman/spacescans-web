/**
 * Exposure-dataset acquisition catalog for the Data Setup page.
 *
 * The DATA lives in data-sources.json (single source of truth) so the backend
 * test tests/test_data_setup_paths.py can read the same file and assert every
 * placeDir still matches a real path in configs/*.yaml — i.e. the guide can't
 * silently drift from where the pipeline actually reads its inputs.
 *
 * Each dataset lists the exposure variableKeys it serves, so the Select
 * Exposures step can link a chosen variable straight to its acquisition entry.
 */
import raw from "./data-sources.json";

export interface DatasetFile {
  name: string;
  note?: string;
}

export interface SelfServeDataset {
  key: string;
  name: string;
  usedBy: string;
  variableKeys: string[];
  role: string;
  sourceName: string;
  sourceUrl: string;
  license: string;
  access: "public" | "account-required";
  size: string;
  files: DatasetFile[];
  placeDir: string[];
  notes: string[];
}

export interface PresetDataset {
  key: string;
  name: string;
  variableKeys: string[];
  role: string;
  artifact: string;
  origin: string;
  placeDir: string[];
}

export const SELF_SERVE_DATASETS = raw.selfServe as SelfServeDataset[];
export const PRESET_DATASETS = raw.preset as PresetDataset[];

/** A dataset entry a given exposure variable depends on, with a stable anchor
 * key into the Data Setup page (/dashboard/data-setup#<key>). */
export interface VariableDatasetLink {
  key: string;
  name: string;
  role: string;
  kind: "self-serve" | "preset";
}

/** Datasets a given exposure variable needs — self-serve inputs first
 * (downloadable), then any preprocessed derivative supplied by the deployer. */
export function datasetsForVariable(variableKey: string): VariableDatasetLink[] {
  const links: VariableDatasetLink[] = [];
  for (const d of SELF_SERVE_DATASETS) {
    if (d.variableKeys.includes(variableKey)) {
      links.push({ key: d.key, name: d.name, role: d.role, kind: "self-serve" });
    }
  }
  for (const d of PRESET_DATASETS) {
    if (d.variableKeys.includes(variableKey)) {
      links.push({ key: d.key, name: d.name, role: d.role, kind: "preset" });
    }
  }
  return links;
}
