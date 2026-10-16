"""SPACESCANS web backend."""

import os

# PROJ must not download transformation grids. The backend image's conda-forge PROJ
# activation exports PROJ_NETWORK=ON (the grids package proj-data is not installed), so
# every EPSG:4326 -> EPSG:5070 transformation tried to fetch a NOAA grid (for example
# us_noaa_inhpgn.tif) from cdn.proj.org. That is an outbound request that depends on where
# the cohort's locations are, and it makes results depend on network access. In threads
# (the API registers datasets in a thread pool) the download failed on the CA bundle and
# pyproj returned inf: a features dataset was stored with infinite coordinates and linked
# nothing (phase-D integration gate, PHASE_D 7.2 I2). With the network off PROJ uses the
# transformation it has locally, the same one the spacescans package computes on a machine
# without network grids, in every thread. Set here, before anything uses PROJ: every web
# process (API, dispatcher, runners) imports this package first, and the pipeline
# subprocesses inherit the environment.
os.environ["PROJ_NETWORK"] = "OFF"
