"""Reproduce the PROJ network failure the phase-D gate found (run inside the backend image).

    docker run --rm -v "$PWD/docs/phaseD-gate:/probe:ro" tier2-d-backend:integration \
        python /probe/proj_network_probe.py            # as the image's env sets it: ON
    docker run --rm -e PROJ_NETWORK_PROBE=OFF -v "$PWD/docs/phaseD-gate:/probe:ro" \
        tier2-d-backend:integration python /probe/proj_network_probe.py

The image's conda activation exports PROJ_NETWORK=ON. With it, the first pyproj
transformation in a worker thread tries to download a NOAA grid from cdn.proj.org and
fails (inf); the main thread downloads it. With PROJ_NETWORK=OFF (what app/__init__.py
sets) every thread gives the same, local result.
"""
import os
import threading

if os.environ.get("PROJ_NETWORK_PROBE"):
    os.environ["PROJ_NETWORK"] = os.environ["PROJ_NETWORK_PROBE"]
from pyproj import Transformer  # noqa: E402

print("PROJ_NETWORK =", os.environ.get("PROJ_NETWORK"))


def transform(label):
    t = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    try:
        print(label, t.transform(-86.15, 39.77, errcheck=True))
    except Exception as exc:  # noqa: BLE001
        print(label, "ERROR", str(exc)[:200])


worker = threading.Thread(target=transform, args=("worker thread (first use):",))
worker.start()
worker.join()
transform("main thread:")
