# pipeline-data/ — exposure data root

This folder is the pipeline's data root (`SPACESCANS_DATA_DIR` → mounted at
`/project` in Docker). **The big raw datasets are gitignored** — several GB,
never committed. What ships with the repo: the folder skeleton (a `.gitkeep`
per dataset dir), this README, the FARA lookup table
(`FARA/C4/varnameCountRemoved.csv`), and the four small deployer artifacts
(NDI, Walkability, CBP + ZBP) — so those three variables work straight from
a clone with nothing to download.

Drop the data in the layout below. Config templates reference these paths
relative to the data root (e.g. `Walkability/C4/...`), so the subfolder
structure matters — this is not a flat dump.

> Already have the data elsewhere (e.g. the parent `spacescans-project` repo)?
> Don't copy it — set `SPACESCANS_DATA_HOST=/abs/path/to/that/root` in `.env`
> and Docker mounts it instead of this folder.

---

## Expected layout

```
pipeline-data/
├── NDI/C4/                                 ndi_bg_acs5_..._xgboost.rds  (ships with the repo)
├── Walkability/C4/                         epawalkind_nationwide_2016_2021.Rda  (ships with the repo)
├── Community_Organization_Density/C4/      cbp_nationwide_*.Rda , zbp_nationwide_*.Rda  (ship with the repo)
├── FARA/C4/                                fara_nationwide_2010_2019_interpolated.Rda  (deployer artifact; varnameCountRemoved.csv ships with the repo)
├── cache/C3/nhd_features/                  tile_gx*_gy*_{flow,water,area,coast}.parquet  (pretiled NHDPlus HR — download the deployer's archive; raw GDB not needed)
├── Noise/C3/                               CONUS_*_L50dBA_*.tif  (NPS soundscape noise)
├── VNL/C3/                                 VNL_v21_npp_*.tif  (VIIRS nighttime lights)
├── TEMIS/C3/                               temis_template.tif  (ships with the repo)
├── TEMIS/C4/raw/                           uvddc/ uvdec/ ...  (KNMI TEMIS UV)
├── cache/C3/tiger_roads_filtered/          {year}/{SSCCC}.parquet  (prefiltered TIGER roads — download the deployer's archive; raw Census zips not needed)
├── County/C3/                              tl_2010_us_county10/*.shp  (Census county boundaries)
├── ZCTA5/C3/                               tl_2010_us_zcta510/*.shp  (Census ZCTA5 boundaries)
├── TRACT/C3/                               tl_2010_<ss>_tract10/*.shp  (Census tract boundaries, per state)
└── BG/C3/                                  tiger2010_bg10_states/ , tiger2024_bg_states/  (Census block groups)
```

Only the datasets for the variables you actually run are required.

## Where to get each dataset

The in-app **Data Setup** page (and `frontend/src/lib/data-sources.json`) lists,
per variable, the exact source + download link and which files are
**self-serve** (public downloads: Census TIGER, NHDPlus, VNL, TEMIS, Noise) vs
**deployer-supplied artifacts** (NDI / Walkability / CBP-ZBP / FARA — modeled or
repackaged, not directly downloadable).
