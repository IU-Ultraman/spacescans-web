# pipeline-data/ — exposure data root

This folder is the pipeline's data root (`SPACESCANS_DATA_DIR` → mounted at
`/project` in Docker). **The big datasets are gitignored** — never committed.
What ships with the repo: this README, the small committed files marked
"(ships with the repo)" in the tree below, and empty `VNL/` + `TEMIS/C4/raw/`
skeleton dirs (those two are download-it-yourself datasets, so the dirs mark
where the files go). Everything else appears when you extract the OneDrive
archives — they carry their own paths relative to this folder.

Drop the data in the layout below. Config templates reference these paths
relative to the data root (e.g. `Walkability/C4/...`), so the subfolder
structure matters — this is not a flat dump.

> Already have the data elsewhere? Don't copy it — set
> `SPACESCANS_DATA_HOST=/abs/path/to/that/root` in `.env` and Docker mounts
> it instead of this folder.

---

## Expected layout

```
pipeline-data/
├── NDI/C4/                                 ndi_bg_acs5_..._xgboost.rds  (ships with the repo)
├── Walkability/C4/                         epawalkind_nationwide_2016_2021.Rda  (ships with the repo)
├── Community_Organization_Density/C4/      cbp_nationwide_*.Rda , zbp_nationwide_*.Rda  (ship with the repo)
├── FARA/C4/                                fara_nationwide_2010_2019_interpolated.Rda  (OneDrive; varnameCountRemoved.csv ships with the repo)
├── cache/C3/nhd_features/                  tile_gx*_gy*_{flow,water,area,coast}.parquet  (OneDrive; raw GDB not needed)
├── cache/C3/tiger_roads_filtered/          {year}/{SSCCC}.parquet  (OneDrive; raw Census zips not needed)
├── BG/C3/                                  tiger2010_bg10_states/ , tiger2024_bg_states/  (OneDrive)
├── TRACT/C3/                               tl_2010_<ss>_tract10/*.shp  (OneDrive)
├── County/C3/                              tl_2010_us_county10/*.shp  (OneDrive)
├── ZCTA5/C3/                               tl_2010_us_zcta510/*.shp  (OneDrive)
├── Noise/C3/                               CONUS_*_L50dBA_*.tif  (OneDrive)
├── VNL/C3/                                 VNL_v21_npp_*.tif  (EOG — account required)
├── TEMIS/C3/                               temis_template.tif  (ships with the repo)
└── TEMIS/C4/raw/                           uvddc/ uvdec/ ...  (KNMI TEMIS — see group 2)
```

Only the datasets for the variables you actually run are required. The in-app
**Data Setup** page carries the same information per variable, with links.

---

## Where the data comes from

### 1. The deployer's OneDrive folder (one-stop download)

Download everything from **[the shared OneDrive folder](https://indiana-my.sharepoint.com/:f:/g/personal/xai_iu_edu/IgDZCqTyHu9yQLgJdoSpy3SoAbF0Yw5qXC8DuHuDamBnhwI?e=22P4ck)**.

One shared folder holds these archives (each with a `MANIFEST.txt` inside;
verify downloads against the folder's `SHA256SUMS.txt`). Run each command
below from the repo root, exactly as written:

| Archive | Extract with | Why it's on OneDrive instead of an official site |
| --- | --- | --- |
| `tiger_roads_filtered_cache_v1.tar.gz` (1.7 GB) | `tar -xzf tiger_roads_filtered_cache_v1.tar.gz -C pipeline-data/` | **derived cache** — S1100/S1200-filtered roads per (county, year); replaces 28 GB of per-county Census zips *and* the first-run filtering |
| `nhd_features_cache_v1.tar.gz` (36 GB) | `tar -xzf nhd_features_cache_v1.tar.gz -C pipeline-data/` | **derived cache** — pretiled NHDPlus water features; replaces the 61 GB GDB *and* hours of first-run tiling |
| `fara_nationwide_2010_2019_interpolated.Rda` (427 MB) | `mv fara_nationwide_2010_2019_interpolated.Rda pipeline-data/FARA/C4/` | **preprocessed artifact** — interpolated from USDA FARA; not downloadable anywhere else |
| `bg_boundaries_v1.tar.gz` (1.25 GB) | `tar -xzf bg_boundaries_v1.tar.gz -C pipeline-data/` | **too tedious by hand** — 102 statewide shapefile zips (51 × 2010 vintage + 51 × 2020 vintage) |
| `tract_boundaries_v1.tar.gz` (0.33 GB) | `tar -xzf tract_boundaries_v1.tar.gz -C pipeline-data/` | **too tedious by hand** — 51 statewide shapefile zips |
| `county_boundaries_v1.tar.gz` (70 MB) | `tar -xzf county_boundaries_v1.tar.gz -C pipeline-data/` | **convenience** — one-stop with the rest |
| `zcta5_boundaries_v1.tar.gz` (0.49 GB) | `tar -xzf zcta5_boundaries_v1.tar.gz -C pipeline-data/` | **convenience** — one-stop with the rest |
| `noise_v1.tar.gz` (1.11 GB) | `tar -xzf noise_v1.tar.gz -C pipeline-data/` | **convenience** — three NPS TIFs, exact filenames required |

Every archive carries its full path from the data root, so the `tar`
command is identical for all of them.

Everything in this group is either US-federal public domain (Census
TIGER/Line under CC0, USGS NHDPlus, USDA FARA, NPS sound model — free to
use and redistribute, credit the agencies; boundary/roads archives are
repackaged TIGER/Line data) or a project-derived artifact, so
redistribution is unencumbered. Each card in the in-app Data Setup page
also keeps the original-source instructions as a fallback.

### 2. Original sources only (license terms require it)

| Dataset | Where | Why not on Drive |
| --- | --- | --- |
| VNL nighttime lights | EOG (Earth Observation Group) — **free account required** | EOG's own terms gate the download; we can't relay it |
| TEMIS UV (daily HDFs) | KNMI/ESA TEMIS mirror | © KNMI/ESA — credits + no explicit redistribution grant, so each deployment downloads its own copy; the **first run auto-converts** the archive to fast parquet (~2 min, one-time) |
