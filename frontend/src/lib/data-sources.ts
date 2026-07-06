/**
 * Exposure-dataset acquisition catalog for the Data Setup page.
 *
 * These are the server-side datasets the spacescans pipeline links against.
 * They are NOT uploaded by end users (who only upload a patient cohort) — a
 * deployer places them under SPACESCANS_DATA_DIR (the repo's data_full/).
 *
 * Only the self-serve public datasets are listed with full download steps;
 * the preprocessed derivatives (NDI/CBP/walkability/FARA) are summarized as
 * "supplied by the deployer" since they can't be fetched from an official site.
 * Source/license/paths verified 2026-07 against the official sites.
 */

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

export const SELF_SERVE_DATASETS: SelfServeDataset[] = [
  {
    key: "tiger-boundaries",
    name: "Census TIGER/Line boundaries — County, Tract, ZCTA5 (2010)",
    usedBy: "County / Tract / ZCTA5 areal linkages + TIGER road-proximity base",
    sourceName: "US Census Bureau — TIGER/Line 2010",
    sourceUrl: "https://www2.census.gov/geo/tiger/TIGER2010/",
    license: "US federal public domain — free to use and redistribute (cite the Census Bureau).",
    access: "public",
    size: "~600 MB + 51 per-state tract files",
    files: [
      { name: "tl_2010_us_county10.zip", note: "national counties, ~71 MB" },
      { name: "tl_2010_us_zcta510.zip", note: "national ZCTAs, ~500 MB" },
      { name: "tl_2010_{ss}_tract10.zip × 51", note: "no national tract file — one per state (50 + DC)" },
    ],
    placeDir: [
      "data_full/County_FL/C3/tl_2010_us_county10/",
      "data_full/ZCTA5/C3/tl_2010_us_zcta510/",
      "data_full/TRACT/C3/tl_2010_{ss}_tract10/  (one subfolder per state)",
    ],
    notes: [
      "Unzip each archive; put the .shp in a subfolder whose name matches the file basename, with its .shx/.dbf/.prj sidecars alongside.",
      "No reprojection needed — the pipeline buffers/reprojects internally.",
    ],
  },
  {
    key: "bg-boundaries",
    name: "Census Block Group boundaries — 2010 + 2020 vintages",
    usedBy: "NDI + EPA Walkability areal linkages (block-group level)",
    sourceName: "US Census Bureau — TIGER/Line",
    sourceUrl: "https://www2.census.gov/geo/tiger/TIGER2024/BG/",
    license: "US federal public domain — free to use and redistribute.",
    access: "public",
    size: "~750 MB (2020) + per-state 2010",
    files: [
      { name: "tl_2024_{ss}_bg.zip × 51", note: "2020 vintage — or just run the bundled script" },
      { name: "tl_2010_{ss}_bg10.zip × 51", note: "2010 vintage, state-level (not per-county)" },
    ],
    placeDir: [
      "data_full/BG_FL/C3/tiger2024_bg_states/tl_2024_{ss}_bg/",
      "data_full/BG_FL/C3/tiger2010_bg10_states/tl_2010_{ss}_bg10/",
    ],
    notes: [
      "Fastest for 2020: run `bash scripts/download_bg_2020_shapefiles.sh` from the repo root (idempotent).",
      "Join column differs: GEOID10 (2010) vs GEOID (2024). If your download exposes GEOID20, edit join_col in bg_us_2020_demo.yaml.",
    ],
  },
  {
    key: "noise",
    name: "Soundscape noise — L50 dBA (CONUS)",
    usedBy: "Noise exposure (grid)",
    sourceName: "US National Park Service — Geospatial sound modeling (Mennitt et al.)",
    sourceUrl: "https://irma.nps.gov/DataStore/Reference/Profile/2217356",
    license: "US federal public domain.",
    access: "public",
    size: "~1.2 GB (3 GeoTIFFs)",
    files: [
      { name: "CONUS_L50dBA_sumDay_exi.tif", note: "existing (primary)" },
      { name: "CONUS_sumDay_L50dBA_imp.tif", note: "impact (anthropogenic)" },
      { name: "CONUS_sumDay_L50dBA_nat.tif", note: "natural" },
    ],
    placeDir: ["data/Noise/C3/"],
    notes: [
      "Keep the exact filenames — the reader hard-codes all three.",
      "Download only the CONUS_ files; skip the AK_/HI_ variants (different projections).",
      "Provenance: project metadata labels this 'US DOT BTS', but the actual files are the NPS soundscape dataset.",
    ],
  },
  {
    key: "nhdplus",
    name: "USGS NHDPlus High Resolution — National Release 2",
    usedBy: "NHD bluespace (distance to water)",
    sourceName: "USGS — National Hydrography",
    sourceUrl: "https://www.usgs.gov/national-hydrography/access-national-hydrography-products",
    license: "US federal public domain.",
    access: "public",
    size: "~29 GB zipped, ~61 GB unzipped (budget ~90 GB free disk)",
    files: [
      { name: "NHDPlus_H_National_Release_2_GDB.zip", note: "national file geodatabase (.gdb)" },
    ],
    placeDir: ["data_full/NHD/C4/"],
    notes: [
      "Direct link: prd-tnm.s3.amazonaws.com/StagedProducts/Hydrography/NHDPlusHR/National/GDB/NHDPlus_H_National_Release_2_GDB.zip",
      "Unzip to the .gdb directory (keep its name) — no conversion needed.",
    ],
  },
  {
    key: "vnl",
    name: "VIIRS Nighttime Lights — VNL v2.1 (2013–2019)",
    usedBy: "Night-time lights exposure (grid)",
    sourceName: "NOAA / Colorado School of Mines — Earth Observation Group (EOG)",
    sourceUrl: "https://eogdata.mines.edu/products/vnl/",
    license: "Free for research/education; redistributable with attribution.",
    access: "account-required",
    size: "~11 GB each × 7 years (uncompressed)",
    files: [
      { name: "VNL_v21_npp_{year}_global_*.average_masked.dat.tif.gz", note: "one per year 2013–2019; choose the 'average_masked' variant" },
    ],
    placeDir: ["data_full/VNL/C3/"],
    notes: [
      "Requires a free EOG account (login) to download the annual global files.",
      "gunzip each .tif.gz after download; keep the original filenames (the reader parses the year).",
    ],
  },
  {
    key: "temis",
    name: "KNMI TEMIS UV — daily UV index / dose (2013–2019)",
    usedBy: "TEMIS UV exposure (grid)",
    sourceName: "KNMI — TEMIS",
    sourceUrl: "https://www.temis.nl/uvradiation/UVarchive.php",
    license: "Publicly available (attribute KNMI/TEMIS).",
    access: "public",
    size: "~10,000 files, ~29 GB",
    files: [
      { name: "{var}YYYYMMDD.hdf", note: "4 variables (uvief, uvdec, uvdvc, uvddc) — one file per day" },
    ],
    placeDir: ["data_full/TEMIS/C4/raw/{var}/{year}/"],
    notes: [
      "Native HDF-4 — install pyhdf (+ the system HDF4 library) to read it.",
      "Scriptable from the CloudFront mirror: d1qb6yzwaaq4he.cloudfront.net/uvradiation/v2.0/{year}/{mm}/{var}YYYYMMDD.hdf",
      "Layout: one subfolder per variable, then per year.",
    ],
  },
];

export interface PresetDataset {
  name: string;
  artifact: string;
  origin: string;
}

/** Preprocessed derivatives that cannot be self-served from an official site —
 * the deployer/collaborator supplies these (see caveats). Listed for
 * transparency; download steps are intentionally out of scope for now. */
export const PRESET_DATASETS: PresetDataset[] = [
  {
    name: "Neighborhood Deprivation Index (NDI)",
    artifact: "ndi_bg_acs5_..._xgboost.rds",
    origin: "Built from Census ACS 5-year via an xgboost model — no public download.",
  },
  {
    name: "Community Organization Density (CBP / ZBP)",
    artifact: "cbp/zbp_nationwide_*.Rda",
    origin: "Derived from Census County / ZIP Business Patterns (raw CBP/ZBP are public).",
  },
  {
    name: "EPA Walkability Index",
    artifact: "epawalkind_nationwide_2016_2021.Rda",
    origin: "Converted from the EPA Smart Location Database (raw SLD is public).",
  },
  {
    name: "USDA Food Access (FARA)",
    artifact: "fara_nationwide_2010_2019_interpolated.Rda",
    origin: "Interpolated from USDA ERS Food Access Research Atlas (raw FARA is public).",
  },
];
