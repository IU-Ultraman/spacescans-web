# ACAG V5.NA.05 — surface PM2.5 and composition (North America, biweekly)

Source: Washington University Atmospheric Composition Analysis Group (ACAG),
product **V5.NA.05** (total PM2.5) and **V5.NA.05.02** (components), NetCDF,
0.01° × 0.01°, biweekly means. Public, CC BY 4.0.
Landing page: https://sites.wustl.edu/acag/datasets/surface-pm2-5/

## What is here

Years **2013–2019** only (26 biweekly files per year per variable = 182 each),
chosen to match the app's other gridded sources (VNL, TEMIS). Box holds
2000–2023 for every variable; extend by rerunning the downloader with a wider
year range — existing files are skipped.

Layout follows what `spacescans.plugins.readers.acag` expects:

    C4/xNorthAmerica/<SPECIES>/BiWeekly/*.nc        plain estimate
    C4/xNorthAmerica/<SPECIES>_bm/BiWeekly/*.nc     "FromBiomass" variant

The reader derives non-biomass columns (`*_nbm`) as plain minus FromBiomass,
so both variants are required for every species.

| dir      | files | size   |
|----------|-------|--------|
| PM25     | 182 |   3.0G |
| PM25_bm  | 182 |   4.9G |
| SO4      | 182 |   1.1G |
| SO4_bm   | 182 |   1.3G |
| SS       | 182 |   502M |
| SS_bm    | 182 |   162M |
| OM       | 182 |   3.7G |
| OM_bm    | 182 |   4.3G |
| NO3      | 182 |   785M |
| NO3_bm   | 182 |   1.3G |
| NH4      | 182 |   712M |
| NH4_bm   | 182 |   1.1G |
| DUST     | 182 |   966M |
| DUST_bm  | 182 |   158M |
| BC       | 182 |   635M |
| BC_bm    | 182 |   1.5G |

Total: 2,912 files, 26G. Every file verified for the HDF5 magic bytes; 26 files per year per directory.

## Where each variable came from (Box shared folders)

Plain total PM2.5   https://wustl.box.com/s/c3lmvqrvbjcrfpqoxb68nwl9tqhkl81g  → GWRPM25/xNorthAmerica/BiWeekly
Plain components    https://wustl.box.com/s/i15cm0rgyjvbmwwjtomo5tmdmoyekl6g  → NetCDF/GWR<SP>/xNorthAmerica/BiWeekly
FromBiomass total   https://wustl.box.com/s/mfw4pr02b31bnp25jlwn402c93vyfjbq  → PM25/xNorthAmerica/BiWeekly
FromBiomass comps   https://wustl.box.com/s/1zjqdwwcto5huijiluk26qyrmzazhe29  → NetCDF/<SP>/xNorthAmerica/BiWeekly

Box's folder API rejects anonymous calls, and "download folder as ZIP" is
disabled on these shares, so files were enumerated by paging each folder's
HTML prefetch (`?page=N`, 20 items/page) and fetched one at a time via
`index.php?rm=box_download_shared_file&shared_name=…&file_id=f_…`.
Every file was checked for the HDF5 magic bytes before being kept.
Scripts: `boxls.py` (enumerate), `boxdl2.sh` (download) — kept with the
session scratch, not in the repo.

## Known quirks

- BC (black carbon) begins mid-2011 upstream; 2013–2019 is complete.
- FromBiomass files are ~1.5× the size of the plain ones.
- Filenames: `V5NA05.HybridPM25[.FromBiomass].xNorthAmerica.YYYYDDD-YYYYDDD.nc`
  for total; `V5NA05.02.Hybrid<SP>-<SP>[.FromBiomass]...` for components
  (day-of-year ranges).
