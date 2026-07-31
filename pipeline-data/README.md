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

Everything here lives in **[the shared OneDrive folder](https://indiana-my.sharepoint.com/:f:/g/personal/xai_iu_edu/IgDZCqTyHu9yQLgJdoSpy3SoAbF0Yw5qXC8DuHuDamBnhwI?e=22P4ck)**,
which the command below pulls from.

**One command per exposome variable, run from the repo root** — it downloads,
verifies the SHA-256, extracts into place, and deletes the archive (so peak
disk is one archive, not all of them). No browser, no `tar` flags, identical on
macOS and Linux. Some variables need two artifacts (values plus the boundary
geometry they are linked through); pass both to one invocation:

| Exposome variable | On disk | Command |
| --- | --- | --- |
| **Road Proximity** | 3.1 GB | `scripts/fetch_distribution.sh tiger_roads_filtered_cache_v1.tar.gz county_boundaries_v1.tar.gz` |
| **Bluespace** | 50.3 GB | `scripts/fetch_distribution.sh nhd_features_cache_v1.tar.gz` |
| **Food Access (FARA)** | 1.1 GB | `scripts/fetch_distribution.sh fara_nationwide_2010_2019_interpolated.Rda tract_boundaries_v1.tar.gz` |
| **Walkability** | 2.3 GB | `scripts/fetch_distribution.sh bg_boundaries_v1.tar.gz` |
| **NDI** | 2.3 GB | `scripts/fetch_distribution.sh bg_boundaries_v1.tar.gz` |
| **Community Organization Density** | 1.0 GB | `scripts/fetch_distribution.sh zcta5_boundaries_v1.tar.gz county_boundaries_v1.tar.gz` |
| **Noise** | 1.3 GB | `scripts/fetch_distribution.sh noise_v1.tar.gz` |
| **Nighttime Lights (VNL)**, **UV (TEMIS)** | — | not redistributable — see group 2 below |

Walkability and NDI share one archive, as do Road Proximity and Community
Organization Density (both need county boundaries), so the shared parts are not
stored twice — all seven variables together come to **8.5 GB**, plus Bluespace
if you have room.

Walkability, NDI and Community Organization Density also need a preprocessed
`.Rda`/`.rds` panel, but those ship inside the repo — nothing to fetch.

```bash
scripts/fetch_distribution.sh --list     # every artifact with its size
scripts/fetch_distribution.sh --small    # everything EXCEPT Bluespace: the other
                                         # seven variables in one go, 8.5 GB on disk
```

> **Codespaces disk:** a default codespace has ~32 GB, so `--small` fits
> comfortably. Bluespace does not — it needs ~89 GB free while unpacking. Run
> that variable on a machine with real storage, or pick a larger machine type
> when creating the codespace.

Rather not use a terminal? The app's **Data Setup** page also takes archive
uploads, and shows the same per-dataset command.

### 2. Original sources only (license terms require it)

| Dataset | Download what | Put it in |
| --- | --- | --- |
| VNL nighttime lights — [EOG (Earth Observation Group)](https://eogdata.mines.edu/products/vnl/), **free account required** | `VNL_v21_npp_{year}_global_*.average_masked.dat.tif.gz`, one per year **2013–2019** (pick the *average_masked* variant, ~11 GB/year uncompressed). `gunzip` each after download; keep the original filenames — the reader parses the year from them | `pipeline-data/VNL/C3/` |
| TEMIS UV — [KNMI UV archive](https://www.temis.nl/uvradiation/UVarchive.php) | daily `{var}YYYYMMDD.hdf` for the four variables `uvief`, `uvdec`, `uvdvc`, `uvddc`, years **2013–2019** (~10,000 files, ~29 GB). Scriptable from the mirror: `https://d1qb6yzwaaq4he.cloudfront.net/uvradiation/v2.0/{year}/{mm}/{var}YYYYMMDD.hdf` | `pipeline-data/TEMIS/C4/raw/{var}/{year}/` — one folder per variable, then per year (the committed `raw/uv*` dirs mark the spots) |

The first run auto-converts the TEMIS HDFs to compact parquet (one-time,
~2 min); every later run reads parquet in seconds — no manual step.
