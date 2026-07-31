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
  /** Primary one-liner for deployer-distributed artifacts: downloads from the
   * shared folder, verifies the SHA-256 and extracts, all from the repo root.
   * Works the same on macOS and Linux. */
  fetch?: string;
  /** Fallback for an archive you already downloaded: the archive carries
   * data-root-relative paths, so this single command lands everything where
   * the pipeline reads it — placeDir then documents what it creates. */
  extract?: string;
}

export interface PresetDataset {
  key: string;
  name: string;
  variableKeys: string[];
  role: string;
  artifact: string;
  origin: string;
  placeDir: string[];
  /** True when the artifact ships inside the repo (committed under
   * pipeline-data/) — nothing for the user to acquire, so the Data Setup
   * page hides it. Entries stay in the JSON for provenance and so the
   * placeDir guard test keeps covering them. */
  shipped?: boolean;
  /** Set when the deployer distributes the artifact for download (e.g. a
   * OneDrive archive) instead of handing it over out of band. */
  downloadUrl?: string;
  downloadNote?: string;
  /** Primary one-liner that fetches + places this artifact (see
   * SelfServeDataset.fetch). */
  fetchCmd?: string;
}

export const SELF_SERVE_DATASETS = raw.selfServe as SelfServeDataset[];
export const PRESET_DATASETS = (raw.preset as PresetDataset[]).filter(
  (d) => !d.shipped,
);

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

/** The single command that fetches everything a variable needs, or null when
 * nothing is deployer-distributed (VNL and TEMIS must come from their original
 * sources). Several variables need two artifacts — exposure values plus the
 * boundary geometry they are linked through — and the script takes them in one
 * invocation, so a per-dataset command would under-provision the variable. */
export function fetchCommandForVariable(variableKey: string): string | null {
  const artifacts: string[] = [];
  for (const d of SELF_SERVE_DATASETS) {
    if (d.variableKeys.includes(variableKey) && d.fetch) {
      artifacts.push(d.files[0].name);
    }
  }
  for (const d of PRESET_DATASETS) {
    if (d.variableKeys.includes(variableKey) && d.fetchCmd) {
      artifacts.push(d.artifact);
    }
  }
  const unique = Array.from(new Set(artifacts));
  return unique.length
    ? `scripts/fetch_distribution.sh ${unique.join(" ")}`
    : null;
}
