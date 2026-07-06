/**
 * Exposure-dataset acquisition catalog for the Data Setup page.
 *
 * The DATA lives in data-sources.json (single source of truth) so the backend
 * test tests/test_data_setup_paths.py can read the same file and assert every
 * placeDir still matches a real path in configs/*.yaml — i.e. the guide can't
 * silently drift from where the pipeline actually reads its inputs.
 *
 * Only self-serve public datasets carry full download steps; the preprocessed
 * derivatives (NDI/CBP/walkability/FARA) are summarized as deployer-supplied.
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
  name: string;
  artifact: string;
  origin: string;
}

export const SELF_SERVE_DATASETS = raw.selfServe as SelfServeDataset[];
export const PRESET_DATASETS = raw.preset as PresetDataset[];
