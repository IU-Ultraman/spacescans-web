#!/usr/bin/env python
"""Write the C3 template raster that defines ACAG's 0.01° grid.

The grid_weights step needs a georeferenced raster to know where each
template cell sits; the values are irrelevant, only the geotransform and
shape matter. This one matches ACAG V5.NA.05's North America grid exactly:
11,800 × 5,400 cells of 0.01°, edges lon −170 → −52, lat 68 → 14.

The raster is written north-up (row 0 = 68°N) because exactextract rejects
a bottom-up transform outright ("Incompatible extents") — verified — while
the ACAG NetCDFs store latitude ascending. The reader flips each array to
north-up before indexing, so both sides agree on cell 0 = north-west.

Usage:
    python scripts/make_acag_template.py [<out.tif>]
Default output: ../pipeline-data/ACAG/C3/acag_template.tif
"""
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine

WIDTH, HEIGHT = 11_800, 5_400          # lon cells, lat cells
RES = 0.01
LON_MIN, LAT_MAX = -170.0, 68.0       # top-left cell edge

def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else (
        Path(__file__).resolve().parents[2] / "pipeline-data" / "ACAG" / "C3" / "acag_template.tif"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    transform = Affine(RES, 0.0, LON_MIN, 0.0, -RES, LAT_MAX)
    with rasterio.open(
        out, "w", driver="GTiff", height=HEIGHT, width=WIDTH, count=1,
        dtype="uint8", crs="EPSG:4326", transform=transform,
        compress="lzw", tiled=True, blockxsize=512, blockysize=512,
    ) as dst:
        for row0 in range(0, HEIGHT, 512):        # stream zeros; never hold 63 MB
            h = min(512, HEIGHT - row0)
            dst.write(np.zeros((h, WIDTH), dtype="uint8"), 1, window=((row0, row0 + h), (0, WIDTH)))
    with rasterio.open(out) as s:
        print(f"{out}  {s.height}x{s.width} {s.dtypes[0]} crs={s.crs} "
              f"transform={tuple(round(x, 4) for x in s.transform[:6])} "
              f"bounds={tuple(round(b, 3) for b in s.bounds)}  {out.stat().st_size/1024:.0f} KB")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
