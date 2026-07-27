# syntax=docker/dockerfile:1

# Backend: FastAPI API + the spacescans pipeline.
#
# micromamba base. Channel split mirrors the tested `spacescans` conda env:
# the GDAL/C++ layer (libgdal, rasterio, exactextract) comes from conda-forge;
# everything else (geopandas, shapely, pyproj, pandas, duckdb, pyreadr) is pip —
# pulled in below via the wheel's [geo,rda] extras + requirements.txt. Installing
# GDAL via conda-forge is far more reliable than pip-building it.
FROM mambaorg/micromamba:1.5.10

# 1) GDAL/C++ layer from conda-forge (pyreadr/geopandas/etc. are NOT on
#    conda-forge — they come from pip).
RUN micromamba install -y -n base -c conda-forge \
        python=3.12 \
        libgdal \
        rasterio \
        exactextract \
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
#    published to PyPI; the locally-built wheel is installed in the next step.
COPY --chown=$MAMBA_USER:$MAMBA_USER requirements.txt ./
RUN grep -vi "spacescans-pipeline" requirements.txt > /tmp/req.txt \
    && python -m pip install --no-cache-dir -r /tmp/req.txt

# 3) The pipeline package, from the locally-built wheel, WITH its [geo,rda]
#    extras (geopandas / shapely / pyproj / duckdb / pyreadr from pip; rasterio +
#    exactextract already satisfied by conda-forge above, so pip skips them).
#    Provides `import spacescans` and the `spacescans` CLI. Resolve the wheel
#    path first so the [geo,rda] suffix isn't mangled by shell glob brackets.
#    Rebuild + re-copy the wheel into backend/wheels/ when the pipeline bumps.
COPY --chown=$MAMBA_USER:$MAMBA_USER wheels/ /tmp/wheels/
RUN WHEEL=$(ls /tmp/wheels/spacescans_pipeline-*.whl) \
    && python -m pip install --no-cache-dir "${WHEEL}[geo,rda]"

# 4) Backend source.
COPY --chown=$MAMBA_USER:$MAMBA_USER . /app

EXPOSE 8000
# Prod: no --reload.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
