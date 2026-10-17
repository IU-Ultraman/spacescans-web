"""Independent reference for the e2e gate: per-episode and per-participant values of the
three registered datasets, from the generated FILES (not the generator's formulas), with
the PHASE_D 2.2 formula: x_i = sum_e sum_t d_et z_et / sum_e sum_t d_et over periods with
a defined estimate (start and end inclusive); static sources: one period = the episode."""
import json
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer

to5070 = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)


def _days(s, e):
    s, e = date.fromisoformat(s), date.fromisoformat(e)
    return [s + timedelta(days=i) for i in range((e - s).days + 1)]


def reference(data_dir):
    data_dir = Path(data_dir)
    design = json.load(open(data_dir / "design.json"))
    cohort = pd.read_csv(data_dir / "cohort_B.csv", dtype=str)
    daily = pd.read_csv(data_dir / "daily_tract.csv", dtype={"GEOID10": str, "date": str})
    dval = {(g, d): v for g, d, v in daily[["GEOID10", "date", "syn_daily"]].itertuples(index=False)}
    rasters = []
    for p in design["periods"]:
        with rasterio.open(data_dir / "bw" / p["file"]) as src:
            rasters.append((date.fromisoformat(p["start"]), date.fromisoformat(p["end"]),
                            src.read(1), src.nodata, src))
    sites = gpd.read_file(data_dir / "sites.gpkg").to_crs("EPSG:5070")
    tract_of = {(round(t["lon"], 6), round(t["lat"], 6)): t["geoid"] for t in design["locations"]}

    ep_rows = []
    contrib = []  # per episode: {var: (sum d*z, sum d)}
    for row in cohort.itertuples(index=False):
        lon, lat = float(row.longitude), float(row.latitude)
        days = _days(row.startDate, row.endDate)
        acc = {}
        # daily tract table (areal; the 270 m buffer lies inside one tract)
        g = tract_of[(round(lon, 6), round(lat, 6))]
        zs = [dval.get((g, d.isoformat())) for d in days]
        zs = [z for z in zs if z is not None and not (isinstance(z, float) and np.isnan(z))]
        acc["syn_daily"] = (float(sum(zs)), len(zs))
        # biweekly raster (the buffer lies inside one cell)
        sdz, sd = 0.0, 0
        for start, end, arr, nodata, src in rasters:
            r, c = src.index(lon, lat)
            z = float(arr[r, c])
            if nodata is not None and z == nodata:
                continue
            ov = max(0, (min(end, days[-1]) - max(start, days[0])).days + 1)
            if ov:
                sdz += ov * z
                sd += ov
        acc["syn_bw"] = (sdz, sd)
        # point features: planar EPSG:5070 distance to the nearest site, static
        x, y = to5070.transform(lon, lat)
        dist = float(np.min(np.hypot(sites.geometry.x.values - x, sites.geometry.y.values - y)))
        acc["syn_sites_dist_m"] = (dist * len(days), len(days))
        contrib.append((row.pid, acc))
        ep_rows.append({"pid": row.pid, **{v: (a / b if b else np.nan) for v, (a, b) in acc.items()}})
    episodes = pd.DataFrame(ep_rows)

    order = list(dict.fromkeys(cohort["pid"]))
    part_rows = []
    for pid in order:
        out = {"pid": pid}
        for v in ("syn_daily", "syn_bw", "syn_sites_dist_m"):
            num = sum(a[v][0] for p, a in contrib if p == pid)
            den = sum(a[v][1] for p, a in contrib if p == pid)
            out[v] = num / den if den else np.nan
        part_rows.append(out)
    return episodes, pd.DataFrame(part_rows), contrib


if __name__ == "__main__":
    import sys
    e, p, _ = reference(sys.argv[1])
    print(e.shape, p.shape)
    print("missing per var (episode):", e.isna().sum().to_dict())
    print("missing per var (participant):", p.isna().sum().to_dict())
