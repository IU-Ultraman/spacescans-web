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

Three ways to get these in place, all equivalent:

- **Running the app on this machine?** Download from the folder, then run the
  `tar` command in the table below from the repo root.
- **Prefer not to touch a terminal?** Upload the downloaded archive on the
  app's **Data Setup** page — the server verifies its checksum and extracts it
  for you.
- **App running somewhere else** (a Codespace, a remote VM, so there is no
  local copy to upload)? Fetch it straight in, no browser involved:

  ```bash
  scripts/fetch_distribution.sh --list                       # what's available
  scripts/fetch_distribution.sh tract_boundaries_v1.tar.gz   # one artifact
  scripts/fetch_distribution.sh --small                      # all but the 38 GB NHD cache
  ```

  It downloads, verifies the SHA-256, extracts, and deletes the archive, so
  peak disk is one archive rather than all of them.

> **Codespaces disk:** a default codespace has ~32 GB. Everything except the
> NHD cache fits (~5.8 GB downloaded, ~8.6 GB extracted). The NHD cache needs
> ~89 GB and will not fit — run the bluespace variable on a machine with real
> storage, or pick a larger machine type when creating the codespace.

Each archive carries a `MANIFEST.txt` inside; the folder's `SHA256SUMS.txt`
holds the checksums (both the upload panel and the fetch script check them for
you). Run each command below from the repo root, exactly as written:

| Archive — exposome variable(s) it feeds | Extract with |
| --- | --- |
| `tiger_roads_filtered_cache_v1.tar.gz` (1.7 GB) — **Road Proximity** | `tar --exclude='._*' --exclude='.DS_Store' -xzf tiger_roads_filtered_cache_v1.tar.gz -C pipeline-data/` |
| `nhd_features_cache_v1.tar.gz` (36 GB) — **Bluespace** | `tar --exclude='._*' --exclude='.DS_Store' -xzf nhd_features_cache_v1.tar.gz -C pipeline-data/` |
| `fara_nationwide_2010_2019_interpolated.Rda` (427 MB) — **Food Access (FARA)** | `mv fara_nationwide_2010_2019_interpolated.Rda pipeline-data/FARA/C4/` |
| `bg_boundaries_v1.tar.gz` (1.25 GB) — **Walkability + NDI** (2010 & 2020 vintages in one archive) | `tar --exclude='._*' --exclude='.DS_Store' -xzf bg_boundaries_v1.tar.gz -C pipeline-data/` |
| `tract_boundaries_v1.tar.gz` (0.33 GB) — **Food Access (FARA)** | `tar --exclude='._*' --exclude='.DS_Store' -xzf tract_boundaries_v1.tar.gz -C pipeline-data/` |
| `county_boundaries_v1.tar.gz` (70 MB) — **Road Proximity + Community Organization Density** | `tar --exclude='._*' --exclude='.DS_Store' -xzf county_boundaries_v1.tar.gz -C pipeline-data/` |
| `zcta5_boundaries_v1.tar.gz` (0.49 GB) — **Community Organization Density** | `tar --exclude='._*' --exclude='.DS_Store' -xzf zcta5_boundaries_v1.tar.gz -C pipeline-data/` |
| `noise_v1.tar.gz` (1.11 GB) — **Noise** | `tar --exclude='._*' --exclude='.DS_Store' -xzf noise_v1.tar.gz -C pipeline-data/` |

Every archive carries its full path from the data root, so the `tar`
command is identical for all of them. The `--exclude` flags drop macOS
metadata files the archives were packed with: macOS `tar` reabsorbs the `._x`
sidecars silently, but GNU `tar` on Linux would write one junk `._file` beside
every real file (~15k of them for the NHD cache). Nothing reads them either way —
every dataset is resolved by exact filename — so an extraction done without
the flag is safe, just untidy. GNU tar also prints
`Ignoring unknown extended header keyword 'LIBARCHIVE.xattr...'` for these
archives; that warning is harmless.

Everything in this group is either US-federal public domain (Census
TIGER/Line under CC0, USGS NHDPlus, USDA FARA, NPS sound model — free to
use and redistribute, credit the agencies; boundary/roads archives are
repackaged TIGER/Line data) or a project-derived artifact, so
redistribution is unencumbered. Each card in the in-app Data Setup page
also keeps the original-source instructions as a fallback.

### 2. Original sources only (license terms require it)

| Dataset | Download what | Put it in |
| --- | --- | --- |
| VNL nighttime lights — [EOG (Earth Observation Group)](https://eogdata.mines.edu/products/vnl/), **free account required** | `VNL_v21_npp_{year}_global_*.average_masked.dat.tif.gz`, one per year **2013–2019** (pick the *average_masked* variant, ~11 GB/year uncompressed). `gunzip` each after download; keep the original filenames — the reader parses the year from them | `pipeline-data/VNL/C3/` |
| TEMIS UV — [KNMI UV archive](https://www.temis.nl/uvradiation/UVarchive.php) | daily `{var}YYYYMMDD.hdf` for the four variables `uvief`, `uvdec`, `uvdvc`, `uvddc`, years **2013–2019** (~10,000 files, ~29 GB). Scriptable from the mirror: `https://d1qb6yzwaaq4he.cloudfront.net/uvradiation/v2.0/{year}/{mm}/{var}YYYYMMDD.hdf` | `pipeline-data/TEMIS/C4/raw/{var}/{year}/` — one folder per variable, then per year (the committed `raw/uv*` dirs mark the spots) |

The first run auto-converts the TEMIS HDFs to compact parquet (one-time,
~2 min); every later run reads parquet in seconds — no manual step.
