# EPA FAQSD — daily ozone and PM2.5 by census tract

Source: US EPA, Fused Air Quality Surface Using Downscaling (FAQSD), the
"outputs" files under RSIG. Public domain.
https://www.epa.gov/hesc/rsig-related-downloadable-data-files#faqsd

## What is here

`C4/{year}_ozone_daily_8hour_maximum.txt` and `C4/{year}_pm25_daily_average.txt`
for **2013–2019**, one row per (day, census tract), ~26.4 million rows and
~1.5 GB each. Values are the fused daily 8-hour maximum ozone (ppb) and the
daily average PM2.5 (µg/m³) at the 2010 tract level.

The reader (`spacescans.plugins.readers.faqsd`) lists files by these exact
names, so keep them as published.

## Where it came from

    https://ofmpub.epa.gov/rsig/rsigserver?data/FAQSD/outputs/{year}_pm25_daily_average.txt.gz
    https://ofmpub.epa.gov/rsig/rsigserver?data/FAQSD/outputs/{year}_ozone_daily_8hour_maximum.txt.gz

Downloaded as .gz, size-checked against Content-Length and the gzip magic,
then unpacked. 2013–2015 were already on this machine from the earlier
per-source pipeline and are hard-linked in rather than copied; 2016–2019
were fetched fresh. EPA publishes 2002–2022.

## Header quirk

EPA switched header styles between years:

    2013–14, 2017–19:  Date,FIPS,Longitude,Latitude,<value>,<stderr>       dates 2017/01/01
    2015–16:           Date,Loc_Label1,Latitude,Longitude,Prediction,SEpred  dates Jan-01-2016

Column *positions* 0/1/4 (date, tract, value) are the same in both, which
is how the reader takes them; it parses both date formats. Latitude and
longitude swap places between styles, but the reader never uses them.

## In the app

Linked as `faqsd` (Tract areal): the 270 m residential buffer's tract area
weights — the same table Food Access computes — weight each day's tract
values, then the days inside each episode are averaged. Output columns are
`faqsd_o3` and `faqsd_pm25` (the source prefix keeps them apart from ACAG's
`pm25`).
