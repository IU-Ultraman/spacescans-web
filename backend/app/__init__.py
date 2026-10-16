"""SPACESCANS web backend."""

# Load pyproj's PROJ library before anything loads rasterio's (GDAL's). In the backend
# image GDAL and rasterio come from conda-forge (PROJ 9.7) and pyproj from pip, which
# bundles its own PROJ (9.8): two PROJ libraries in one process. When rasterio is
# imported first, pyproj's transformations return inf until GDAL happens to initialise
# PROJ, so a features dataset registered after a raster upload got infinite coordinates
# and linked nothing (phase-D integration gate, PHASE_D 7.2 I2). With pyproj first both
# work; it is also the order of the spacescans CLI, which imports geopandas (pyproj)
# before rasterio. Every web process (API, dispatcher, runners) imports this package
# before anything else of the app.
try:
    import pyproj  # noqa: F401
except ImportError:  # a backend installed without the geo extras
    pass
