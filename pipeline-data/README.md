# pipeline-data/ — exposure data root

This folder is the pipeline's data root (`SPACESCANS_DATA_DIR` → mounted at
`/project` in Docker). **The datasets themselves are gitignored** — they are
several GB and must never be committed. What ships with the repo is the empty
folder skeleton (a `.gitkeep` per dataset dir), this README, and one small
lookup table, `FARA/C4/varnameCountRemoved.csv`.

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
├── NDI/C4/                                 ndi_bg_acs5_..._xgboost.rds  (deployer artifact)
├── Walkability/C4/                         epawalkind_nationwide_2016_2021.Rda  (deployer artifact)
├── Community_Organization_Density/C4/      cbp_nationwide_*.Rda , zbp_nationwide_*.Rda  (deployer artifacts)
├── FARA/C4/                                fara_nationwide_2010_2019_interpolated.Rda  (varnameCountRemoved.csv already ships here)
├── NHD/C4/                                 NHDPlus_H_National_Release_2_GDB.gdb  (USGS NHDPlus HR)
├── Noise/C3/                               CONUS_*_L50dBA_*.tif  (NPS soundscape noise)
├── VNL/C3/                                 VNL_v21_npp_*.tif  (VIIRS nighttime lights)
├── TEMIS/C4/raw/                           uvddc/ uvdec/ ...  (KNMI TEMIS UV)
├── TIGER/C4/                               tiger{2013..2019}_roads/  (Census TIGER roads)
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
