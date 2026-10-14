"""Inspect, validate and read user-uploaded GeoTIFFs for custom exposomes.

Shim: the functions live in ``spacescans.custom.raster`` since tier-2 phase B
(a verbatim port of this module). Kept so ``app.raster_values.*`` and its tests
keep working until the cutover. ``FULL_READ_MAX_CELLS`` stays a module global
here and is passed through, so a test that patches it still reaches the
block-wise read path.
"""
from __future__ import annotations

from spacescans.custom import raster as _impl
from spacescans.custom.errors import RasterError  # noqa: F401
from spacescans.custom.raster import (  # noqa: F401
    CONUS_BBOX,
    MAX_BANDS_LISTED,
    _open,
    _resolution_label,
    grid_hash,
    same_grid,
)

FULL_READ_MAX_CELLS = _impl.FULL_READ_MAX_CELLS
inspect = _impl.inspect_raster


def extract_values(raster_path, grid_ids, *, band=1, nodata=None):
    """Pixel values at each grid_id (row-major, 0-based). NaN for nodata or an
    id outside the raster."""
    return _impl.extract_values(raster_path, grid_ids, band=band, nodata=nodata,
                                full_read_max_cells=FULL_READ_MAX_CELLS)


def extract_bands(raster_path, grid_ids, *, bands, nodata=None):
    """Pixel values of several bands at each grid_id: shape (len(grid_ids),
    len(bands)), columns in the order of ``bands``."""
    return _impl.extract_bands(raster_path, grid_ids, bands=bands, nodata=nodata,
                               full_read_max_cells=FULL_READ_MAX_CELLS)
