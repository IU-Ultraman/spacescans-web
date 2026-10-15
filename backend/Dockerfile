# syntax=docker/dockerfile:1

# Backend: FastAPI API + the spacescans pipeline.
#
# micromamba base. Channel split mirrors the tested `spacescans` conda env:
# the GDAL/C++ layer (libgdal, rasterio, exactextract) comes from conda-forge;
# everything else (geopandas, shapely, pyproj, pandas, duckdb, pyreadr) is pip —
# pulled in below via the pipeline's [geo,rda] extras (installed from GitHub) +
# requirements.txt. Installing GDAL via conda-forge beats pip-building it.
FROM mambaorg/micromamba:1.5.10

# 1) GDAL/C++ layer from conda-forge (pyreadr/geopandas/etc. are NOT on
#    conda-forge — they come from pip). `git` is needed to pip-install the
#    pipeline straight from its GitHub repo below. pyhdf comes from
#    conda-forge too — it bundles the HDF4 C library the TEMIS reader needs
#    (without it the plugin silently doesn't register).
RUN micromamba install -y -n base -c conda-forge \
        python=3.12 \
        libgdal \
        rasterio \
        exactextract \
        pyhdf \
        git \
    && micromamba clean --all --yes

# Activate the base env for every RUN / CMD below (so `python` / `pip` resolve
# to the conda env, not the system interpreter).
ARG MAMBA_DOCKERFILE_ACTIVATE=1

# Own /app (incl. the writable data/ mount point) as the mamba user so the API
# process can write the SQLite DB, tasks/, and c3_cache/ at runtime.
USER root
RUN mkdir -p /app/data && chown -R $MAMBA_USER:$MAMBA_USER /app
USER $MAMBA_USER
WORKDIR /app

# 2) Python API deps first (layer caching). Strip the pipeline line — it is not
#    on PyPI; it's installed from GitHub in the next step. requirements.txt
#    pins pandas and pyarrow: the C3 weight-cache keys of the legacy format
#    depend on the pandas patch version (tier-2 phase B, finding #12), so the
#    image must keep the versions the goldens were made with. constraints.txt
#    pins every other package pip installs, here and in step 3, to the versions
#    of the image the tier-2 gates tested: a rebuild (a new SPACESCANS_REF
#    re-runs both steps) would otherwise take whatever PyPI has that day.
COPY --chown=$MAMBA_USER:$MAMBA_USER requirements.txt constraints.txt ./
RUN grep -vi "spacescans-pipeline" requirements.txt > /tmp/req.txt \
    && python -m pip install --no-cache-dir -c constraints.txt -r /tmp/req.txt

# 3) The pipeline package, installed straight from its public GitHub repo
#    (IU-Ultraman/spacescans), pinned to a commit or release tag, WITH its
#    [geo,rda,hdf4,nc] extras (geopandas / shapely / pyproj / duckdb / pyreadr /
#    mercantile from pip; rasterio + exactextract + pyhdf already satisfied by
#    conda-forge above). Provides `import spacescans` (catalog, custom, data,
#    orchestrate) and the `spacescans` CLI the runners call. Bump
#    SPACESCANS_REF to pull a newer release. The pandas / pyarrow pins are
#    repeated so the resolver cannot move them while installing the extras, and
#    constraints.txt holds the extras' dependencies to the tested versions.
ARG SPACESCANS_REF=d92f7a3623ff5c35cde7a296ea6a347d108be5b3
RUN python -m pip install --no-cache-dir -c constraints.txt \
    "pandas==3.0.5" "pyarrow==26.0.0" \
    "spacescans-pipeline[geo,rda,hdf4,nc] @ git+https://github.com/IU-Ultraman/spacescans.git@${SPACESCANS_REF}"

# 4) Backend source.
COPY --chown=$MAMBA_USER:$MAMBA_USER . /app

EXPOSE 8000
# Prod: no --reload.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
