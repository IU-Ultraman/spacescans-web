"""Synthetic inputs for the phase-D web gate. usage: make_data.py <out_dir> <TRACT/C3 dir>

Real 2010 tract polygons are READ (never written) to place each synthetic
location at a tract's pole of inaccessibility such that a 400 m circle stays
inside the tract AND inside one cell of the synthetic 0.1-degree raster grid:
then the 270 m buffer's areal and raster means equal one tract value / one
cell value, and the hand reference is exact.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from pyproj import Transformer
import shapely
from shapely.geometry import Point, box
from shapely.ops import polylabel

OUT = Path(sys.argv[1])
TRACTS = Path(sys.argv[2])  # .../pipeline-data/TRACT/C3 (read-only)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "bw").mkdir(exist_ok=True)

to5070 = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
to4326 = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)

# raster grid: 0.1 degree over the CONUS box
X0, Y0, RES = -125.0, 50.0, 0.1
W, H = 590, 260


def cell_of(lon, lat):
    return int((Y0 - lat) // RES), int((lon - X0) // RES)


def cell_box(r, c):
    return box(X0 + c * RES, Y0 - (r + 1) * RES, X0 + (c + 1) * RES, Y0 - r * RES)


def pick(state, counties, n, seed):
    shp = TRACTS / f"tl_2010_{state}_tract10" / f"tl_2010_{state}_tract10.shp"
    g = gpd.read_file(shp)
    g = g[g["COUNTYFP10"].isin(counties)].sort_values("GEOID10").reset_index(drop=True)
    g5070 = g.to_crs("EPSG:5070")
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(g))
    chosen = []
    for i in order:
        poly = g5070.geometry.iloc[i]
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda p: p.area)
        p = polylabel(poly, tolerance=5.0)
        circle = p.buffer(400.0)
        if not poly.contains(circle):
            continue
        lon, lat = to4326.transform(p.x, p.y)
        r, c = cell_of(lon, lat)
        circle4326 = shapely.transform(
            circle, lambda xy: np.column_stack(to4326.transform(xy[:, 0], xy[:, 1])))
        if not cell_box(r, c).contains(circle4326):
            continue
        if any((r, c) == (q["row"], q["col"]) for q in chosen):
            continue  # one location per raster cell
        chosen.append({"geoid": g["GEOID10"].iloc[i], "lon": round(lon, 6), "lat": round(lat, 6),
                       "row": r, "col": c, "state": state})
        if len(chosen) == n:
            break
    assert len(chosen) == n, (state, len(chosen))
    return chosen, g


inn, g_in = pick("18", ["097", "057", "063", "081"], 6, 7)
ill, g_il = pick("17", ["197", "091"], 2, 11)
locs = inn + ill  # T0..T5 Indiana, T6..T7 Illinois
# re-read the exact coordinates as written (6 decimals) for the reference
for t in locs:
    x, y = to5070.transform(t["lon"], t["lat"])
    t["x5070"], t["y5070"] = x, y
    t["row"], t["col"] = cell_of(t["lon"], t["lat"])

D = lambda s: date.fromisoformat(s)
# (pid, tract index, start, end); rows interleaved to test first-appearance order
episodes = [
    ("00102", 2, "2016-01-01", "2016-03-31"),
    ("00101", 0, "2016-01-05", "2016-02-10"),
    ("00103", 3, "2016-03-01", "2016-04-30"),
    ("00102", 6, "2016-02-01", "2016-02-10"),   # overlaps 00102's first episode
    ("00105", 4, "2016-01-20", "2016-02-05"),   # meets T4's missing-value window
    ("00101", 1, "2016-02-11", "2016-03-20"),
    ("00104", 4, "2015-06-01", "2015-06-30"),   # before every dated period
    ("00106", 7, "2016-01-10", "2016-02-15"),   # T7's cell is nodata in period 2
    ("00105", 5, "2016-02-20", "2016-03-05"),
    ("00106", 6, "2016-02-16", "2016-03-10"),
    ("00105", 0, "2016-03-15", "2016-03-31"),
]
rows = []
for pid, ti, s, e in episodes:
    t = locs[ti]
    rows.append({"pid": pid, "startDate": s, "endDate": e, "longitude": t["lon"],
                 "latitude": t["lat"], "state_fips": t["state"]})
pd.DataFrame(rows).to_csv(OUT / "cohort_B.csv", index=False)

# daily tract table: the 8 location tracts + 4 others, 2016-01-01..2016-03-31
extra = [g for g in g_in["GEOID10"].tolist() if g not in {t["geoid"] for t in locs}][:4]
tract_ids = [t["geoid"] for t in locs] + extra
day0 = D("2016-01-01")
ndays = 91
MISSING = {(4, d) for d in range(31, 38)}  # T4, 2016-02-01..2016-02-07
lines = ["GEOID10,date,syn_daily"]
for i, g in enumerate(tract_ids):
    for d in range(ndays):
        val = "" if (i, d) in MISSING else f"{10 * (i + 1) + 0.1 * d:.1f}"
        lines.append(f"{g},{(day0 + timedelta(days=d)).isoformat()},{val}")
(OUT / "daily_tract.csv").write_text("\n".join(lines) + "\n")

# biweekly rasters: 6 periods of 14 days from 2016-01-01; float32 exact values
NODATA = -9999.0
periods = []
for k in range(6):
    start = day0 + timedelta(days=14 * k)
    end = start + timedelta(days=13)
    rr, cc = np.mgrid[0:H, 0:W]
    arr = (100.0 * (k + 1) + rr + cc / 8.0).astype("float32")
    if k == 2:
        r7, c7 = locs[7]["row"], locs[7]["col"]
        arr[r7, c7] = NODATA
    name = f"syn_bw_{start:%Y%m%d}_{end:%Y%m%d}.tif"
    with rasterio.open(OUT / "bw" / name, "w", driver="GTiff", height=H, width=W, count=1,
                       dtype="float32", crs="EPSG:4326", transform=from_origin(X0, Y0, RES, RES),
                       nodata=NODATA, compress="deflate") as dst:
        dst.write(arr, 1)
    periods.append({"file": name, "start": start.isoformat(), "end": end.isoformat()})

# point features (EPSG:4326 GeoPackage), 25 points over central IN / NE IL
rng = np.random.default_rng(2026)
pts = [Point(float(x), float(y)) for x, y in zip(rng.uniform(-88.5, -85.5, 25),
                                                  rng.uniform(39.3, 42.0, 25))]
gpd.GeoDataFrame({"site": [f"S{i:02d}" for i in range(25)]}, geometry=pts,
                 crs="EPSG:4326").to_file(OUT / "sites.gpkg", driver="GPKG")

# private static tract table (user A keeps it private)
pl = ["GEOID10,syn_private"] + [f"{g},{i + 0.5}" for i, g in enumerate(tract_ids)]
(OUT / "private_static.csv").write_text("\n".join(pl) + "\n")

json.dump({"locations": locs, "episodes": episodes, "tract_ids": tract_ids,
           "periods": periods, "grid": {"x0": X0, "y0": Y0, "res": RES, "w": W, "h": H},
           "daily_first": day0.isoformat(), "daily_days": ndays},
          open(OUT / "design.json", "w"), indent=1)
print("ok: locations", len(locs), "episodes", len(episodes), "daily rows", len(lines) - 1,
      "periods", len(periods))
