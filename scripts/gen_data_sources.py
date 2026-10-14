#!/usr/bin/env python3
"""Generate frontend/src/lib/data-sources.json from the spacescans data manifest.

The Data Setup page's acquisition catalog used to be hand-written. Since tier-2
phase B the spacescans package carries the data manifest
(``spacescans/data/manifest.json``): every mirrored artifact with its sha256 and
sizes, every dataset with its provider, licence, attribution, source URL,
acquisition mode, terms and on-disk layout, and which datasets each catalog
variable needs. Everything structural in the page comes from there now:

* which exposure variables a dataset serves (``variableKeys``);
* the artifact file names, their sizes and the ``fetch`` / ``extract`` commands;
* where the files land (``placeDir``, from the layout rules or the artifact
  destination), which ``backend/tests/test_data_setup_paths.py`` checks against
  the pipeline templates;
* provider, source URL, licence and attribution, and whether an account is
  needed (``access``);
* the mirror link of the deployer-distributed files.

What the manifest does not carry is the page's prose: the card titles, the
one-line "used by", the role labels, the notes and the file-pattern hints for
provider datasets. That stays in the PRESENTATION table below, keyed by card.

Run from the repo root with a Python that has spacescans installed (the
backend's):

    python scripts/gen_data_sources.py            # rewrite the JSON
    python scripts/gen_data_sources.py --check    # exit 1 when the file is stale
"""
from __future__ import annotations

import argparse
import json
import posixpath
import sys
from pathlib import Path
from typing import Any

from spacescans.data import load_manifest
from spacescans.data.manifest import Artifact, Dataset, Manifest

REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / "frontend" / "src" / "lib" / "data-sources.json"

FETCH_SCRIPT = "scripts/fetch_distribution.sh"
EXTRACT_CMD = "tar --exclude='._*' --exclude='.DS_Store' -xzf {name} -C pipeline-data/"
MACOS_NOTE = ("The two --exclude flags drop macOS metadata files the archive was packed "
              "with — harmless, but GNU tar (Linux) would otherwise write one junk ._file "
              "per real file.")
MIRROR_SOURCE_NAME = {"iu-onedrive": "Deployer-distributed archive (OneDrive)"}
MIRROR_FILE_NOTE = "MANIFEST.txt inside; sha256 and size in the spacescans data manifest (SHA256SUMS.txt in the OneDrive folder)"

# One card per entry: (card key, manifest dataset key, prose and overrides).
# ``layout`` picks the layout rules a card documents (default: all);
# ``variableKeys`` overrides the derived list where one dataset serves two
# cards (the BG archive holds both vintages, and only NDI uses the 2020 one).
SELF_SERVE: list[tuple[str, str, dict[str, Any]]] = [
    ("county-boundaries", "county_boundaries", {
        "name": "Census County boundaries (2010)",
        "usedBy": "TIGER road-proximity clip base; CBP county fallback",
        "role": "Boundary geometry",
        "notes": [
            "Prefer the original source? tl_2010_us_county10.zip (the single NATIONAL file) from "
            "https://www2.census.gov/geo/tiger/TIGER2010/COUNTY/2010/ — unzip into County/C3/tl_2010_us_county10/.",
            "No reprojection needed — the pipeline buffers/reprojects internally.",
        ],
    }),
    ("tract-boundaries", "tract_boundaries", {
        "name": "Census Tract boundaries (2010)",
        "usedBy": "Tract areal linkage (FARA food access, EPA FAQSD)",
        "role": "Boundary geometry",
        "fileNote": "51 statewide 2010 tract sets; " + MIRROR_FILE_NOTE,
        "notes": [
            "Prefer the original source? Grab the 51 STATEWIDE tl_2010_{ss}_tract10.zip (2-digit FIPS) from "
            "https://www2.census.gov/geo/tiger/TIGER2010/TRACT/2010/ and unzip each into TRACT/C3/.",
        ],
    }),
    ("zcta5-boundaries", "zcta5_boundaries", {
        "name": "Census ZCTA5 boundaries (2010)",
        "usedBy": "ZCTA5 areal linkage (business-patterns / CBP)",
        "role": "Boundary geometry",
        "notes": [
            "Prefer the original source? tl_2010_us_zcta510.zip from "
            "https://www2.census.gov/geo/tiger/TIGER2010/ZCTA5/2010/ — unzip into ZCTA5/C3/tl_2010_us_zcta510/.",
        ],
    }),
    ("tiger-roads", "tiger_roads_cache", {
        "name": "TIGER/Line roads — prefiltered cache",
        "usedBy": "TIGER road proximity (distance to nearest road)",
        "role": "Road geometry",
        "fileNote": ("S1100/S1200 roads, one parquet per (county, year), all 22,618 county-years "
                     "2013–2019; " + MIRROR_FILE_NOTE),
        "notes": [
            "That's it — no raw Census downloads and no first-run filtering; runs read the parquet cache directly.",
            "Advanced fallback: raw per-county zips are still supported at TIGER/C4/tiger{year}_roads/ "
            "(the pre-flight accepts either form, per year).",
        ],
    }),
    ("bg-boundaries-2010", "bg_boundaries", {
        "name": "Census Block Group boundaries — 2010 vintage",
        "usedBy": "EPA Walkability + NDI (ACS periods with end year < 2020)",
        "role": "Boundary geometry",
        "layout": [0],
        "variableKeys": ["walkability", "ndi"],
        "fileNote": ("51 statewide 2010-vintage sets AND the 51 2020-vintage sets in one archive; "
                     + MIRROR_FILE_NOTE),
        "notes": [
            "One download covers this card AND the 2020-vintage card below.",
            "Prefer the original source? Grab the 51 statewide tl_2010_{ss}_bg10.zip from "
            "https://www2.census.gov/geo/tiger/TIGER2010/BG/2010/ (2-digit state FIPS, not the 5-digit "
            "per-county files) and unzip each into BG/C3/tiger2010_bg10_states/.",
        ],
    }),
    ("bg-boundaries-2020", "bg_boundaries", {
        "name": "Census Block Group boundaries — 2020 vintage (TIGER 2024)",
        "usedBy": "NDI only (ACS periods with end year ≥ 2020)",
        "role": "Boundary geometry",
        "layout": [1],
        "variableKeys": ["ndi"],
        "size": "included in bg_boundaries_v1.tar.gz (see the 2010 card)",
        "fileNote": "same archive as the 2010-vintage card — one download covers both; " + MIRROR_FILE_NOTE,
        "notes": [
            "Prefer the original source? Grab the 51 statewide tl_2024_{ss}_bg.zip from "
            "https://www2.census.gov/geo/tiger/TIGER2024/BG/ and unzip each into BG/C3/tiger2024_bg_states/.",
            "Join column is GEOID (some products expose GEOID20 — if so, edit join_col in bg_us_2020_demo.yaml).",
            "Only NDI needs the 2020 vintage — its ACS 2020-2024 periods use 2020-Census BG boundaries; "
            "walkability does not.",
        ],
    }),
    ("noise", "noise_rasters", {
        "name": "Soundscape noise — L50 dBA (CONUS)",
        "usedBy": "Noise exposure (grid)",
        "role": "Gridded values",
        "notes": [
            "Prefer the original source? Download the three CONUS_ TIFs from the NPS DataStore "
            "(https://irma.nps.gov/DataStore/Reference/Profile/2217356); skip the AK_/HI_ variants.",
            "No census boundary file needed — values are linked straight from each patient's 270 m "
            "residential buffer onto this raster grid (grid_weights), not via block-group polygons.",
            "Keep the exact filenames — the reader hard-codes all three.",
            "Download only the CONUS_ files; skip the AK_/HI_ variants (different projections).",
            "Provenance: project metadata labels this 'US DOT BTS', but the actual files are the NPS "
            "soundscape dataset.",
        ],
    }),
    ("nhdplus", "nhd_features_cache", {
        "name": "NHDPlus HR water features — pretiled cache",
        "usedBy": "NHD bluespace (distance to water)",
        "role": "Water geometry",
        "fileNote": ("flow/water/area/coast features per 0.5° tile, full CONUS (14,856 parquets); "
                     + MIRROR_FILE_NOTE),
        "notes": [
            "That's it — no 61 GB NHDPlus GDB download and no first-run tiling.",
            "Advanced fallback: the raw GDB is still supported at NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb "
            "(either form satisfies the pre-flight; a tile-cache miss without the GDB fails with a clear "
            "error rather than a wrong value).",
        ],
    }),
    ("vnl", "vnl", {
        "name": "VIIRS Nighttime Lights — VNL v2.1 (2013–2019)",
        "usedBy": "Night-time lights exposure (grid)",
        "role": "Gridded values",
        "files": [
            {"name": "VNL_v21_npp_{year}_global_*.average_masked.dat.tif.gz",
             "note": "one per year 2013–2019; choose the 'average_masked' variant"},
        ],
        "notes": [
            "No census boundary file needed — values are linked straight from each patient's 270 m "
            "residential buffer onto this raster grid (grid_weights), not via block-group polygons.",
            "Requires a free EOG account (login) to download the annual global files.",
            "gunzip each .tif.gz after download; keep the original filenames (the reader parses the year).",
        ],
    }),
    ("temis", "temis_uv_raw", {
        "name": "KNMI TEMIS UV — daily UV index / dose (2013–2019)",
        "usedBy": "TEMIS UV exposure (grid)",
        "role": "Gridded values",
        "files": [
            {"name": "{var}YYYYMMDD.hdf",
             "note": "4 variables (uvief, uvdec, uvdvc, uvddc) — one file per day"},
        ],
        "notes": [
            "No census boundary file needed — values are linked straight from each patient's 270 m "
            "residential buffer onto this raster grid (grid_weights), not via block-group polygons.",
            "Native HDF-4 — install pyhdf (+ the system HDF4 library) to read it.",
            "Scriptable: `spacescans data fetch --dataset temis_uv_raw --accept-terms knmi-temis` downloads "
            "every day from the CloudFront mirror d1qb6yzwaaq4he.cloudfront.net/uvradiation/v2.0/{year}/{mm}/{var}YYYYMMDD.hdf",
            "Layout: one subfolder per variable, then per year.",
            "The first run auto-converts the HDF archive to compact parquet (one-time, ~2 min); every later "
            "run reads parquet in seconds. No manual step needed.",
            "Data © KNMI/ESA (https://www.temis.nl/), used with credits; neither the raw HDFs nor the "
            "converted parquet are redistributed with this repo — each deployment downloads its own copy "
            "and converts locally.",
        ],
    }),
    ("acag", "acag", {
        "name": "ACAG PM2.5 composition — V5.NA.05 biweekly (2013–2019)",
        "usedBy": "ACAG PM2.5 composition (grid)",
        "role": "Gridded values",
        "files": [
            {"name": "V5NA05.HybridPM25[.FromBiomass].xNorthAmerica.YYYYDDD-YYYYDDD.nc",
             "note": "total PM2.5, 26 biweekly files per year"},
            {"name": "V5NA05.02.Hybrid<SP>-<SP>[.FromBiomass].xNorthAmerica.YYYYDDD-YYYYDDD.nc",
             "note": "seven components: BC, DUST, NH4, NO3, OM, SO4, SS"},
        ],
        "notes": [
            "No census boundary file needed — values are linked straight from each patient's 270 m "
            "residential buffer onto the 0.01° grid (grid_weights); the template raster "
            "ACAG/C3/acag_template.tif ships with the repo.",
            "Both variants are required: the linkage derives each species' non-biomass share as plain "
            "minus FromBiomass.",
            "Scriptable: `spacescans data fetch --dataset acag --accept-terms acag-v5na05` fetches the files "
            "one by one from the four WashU Box shares (the folder API rejects anonymous calls and 'download "
            "folder' is disabled); pipeline-data/ACAG/README.md documents the folder IDs.",
            "{dir} is PM25, BC, DUST, NH4, NO3, OM, SO4, SS for the plain surfaces and the same names with "
            "_bm for the FromBiomass ones.",
            "Years 2000–2023 are available upstream; 2013–2019 matches the app's other gridded sources.",
        ],
    }),
    ("faqsd", "faqsd", {
        "name": "EPA FAQSD — daily ozone and PM2.5 by census tract (2013–2019)",
        "usedBy": "EPA FAQSD air quality (tract areal)",
        "role": "Exposure values",
        "files": [
            {"name": "{year}_ozone_daily_8hour_maximum.txt",
             "note": "one per year; download the .txt.gz and gunzip"},
            {"name": "{year}_pm25_daily_average.txt",
             "note": "one per year; download the .txt.gz and gunzip"},
        ],
        "notes": [
            "Needs the 2010 Census Tract boundaries (TRACT/C3) — the same tract weight table Food Access "
            "uses, and a cohort that has run either gets the other's rasterization from cache.",
            "Scriptable: `spacescans data fetch --dataset faqsd --accept-terms epa-faqsd`, or by hand from "
            "https://ofmpub.epa.gov/rsig/rsigserver?data/FAQSD/outputs/{year}_{pm25_daily_average|ozone_daily_8hour_maximum}.txt.gz",
            "EPA switched header styles between years (FIPS/value vs Loc_Label1/Prediction, and two date "
            "formats); the reader takes columns by position and parses both date styles, so keep the files "
            "exactly as published.",
        ],
    }),
]

# Deployer-supplied exposure tables. ``shipped`` marks the ones committed under
# pipeline-data/ (nothing to acquire; the page hides them).
PRESET: list[tuple[str, str, dict[str, Any]]] = [
    ("ndi-artifact", "ndi_panel", {
        "name": "Neighborhood Deprivation Index (NDI)",
        "shipped": True,
        "artifact": "ndi_bg_acs5_..._xgboost.rds",
        "origin": "Built from Census ACS 5-year via an xgboost model — no public download.",
    }),
    ("cbp-artifact", "cbp_panels", {
        "name": "Community Organization Density (ZBP + county CBP)",
        "shipped": True,
        "artifact": "zbp_nationwide_*.Rda + cbp_nationwide_*.Rda",
        "origin": ("Derived from Census ZIP + County Business Patterns (raw ZBP/CBP are public). ZBP gives "
                   "ZCTA5-level density; patients whose ZIP has no ZBP row fall back to their county's CBP "
                   "— so BOTH files are needed. The fallback also reuses the ZBP linkage output internally "
                   "(auto-generated per run, not a download)."),
    }),
    ("walkability-artifact", "walkability_panel", {
        "name": "EPA Walkability Index",
        "shipped": True,
        "origin": ("Converted from the EPA Smart Location Database (raw SLD is public). The pipeline uses "
                   "the 2016 year as a static index; the file's 2021 rows are filtered out."),
    }),
    ("fara-artifact", "fara_panel", {
        "name": "USDA Food Access (FARA)",
        "artifact": "fara_nationwide_2010_2019_interpolated.Rda",
        "origin": "Interpolated from USDA ERS Food Access Research Atlas (raw FARA is public).",
    }),
]


# ---------------------------------------------------------------------------
# derivations from the manifest
# ---------------------------------------------------------------------------

def _size(nbytes: int) -> str:
    if nbytes >= 1e9:
        return f"{nbytes / 1e9:.2f} GB"
    return f"{nbytes / 1e6:.0f} MB"


def variable_keys(manifest: Manifest, dataset: str) -> list[str]:
    """Catalog variables that need ``dataset`` (as one of a requirement's alternatives)."""
    return [key for key, needs in manifest.variables.items()
            if any(dataset in req.any_of for req in needs.requires)]


def place_dirs(dataset: Dataset, artifacts: list[Artifact], indices: list[int] | None) -> list[str]:
    """Where the dataset's files land, from its layout rules (or the artifact
    destinations when it has none), as ``dir/`` with the manifest's placeholders."""
    out: list[str] = []
    for i, rule in enumerate(dataset.layout):
        if indices is not None and i not in indices:
            continue
        if rule["rule"] in ("files", "daily"):
            d = posixpath.dirname(rule["path"])
        else:
            d = rule.get("dir") or rule.get("path")
        d = d.rstrip("/") + "/"
        if d not in out:
            out.append(d)
    if not out:
        for art in artifacts:
            for d in ([art.dest] if art.kind == "bare" else list(art.roots)):
                d = d.rstrip("/") + "/"
                if d not in out:
                    out.append(d)
    return out


def licence_text(dataset: Dataset) -> str:
    """Licence, redistribution term and attribution, as one line for the page.

    The manifest's ``redistribution`` field is the term, sometimes followed
    by maintainer notes after a semicolon (why an older note was superseded,
    how sites acquire the data); the page shows the term only. A licence
    string that already carries a redistribution clause of its own gives way
    to that term, so the line does not state it twice.
    """
    clauses = [c.strip() for c in dataset.license.split(";") if c.strip()]
    clauses = [c for c in clauses if not c.lower().startswith("redistribution")]
    term = dataset.redistribution.split(";")[0].strip()
    return f"{'; '.join(clauses)}; redistribution {term}. {dataset.attribution}"


def estimate_text(dataset: Dataset) -> str:
    dl = dataset.estimate.get("download_bytes")
    disk = dataset.estimate.get("disk_bytes")
    if dl and disk and dl != disk:
        return f"about {_size(dl)} to download, {_size(disk)} on disk"
    if disk or dl:
        return f"about {_size(disk or dl)} on disk"
    return ""


def self_serve_card(manifest: Manifest, key: str, ds_key: str, prose: dict[str, Any]) -> dict[str, Any]:
    ds = manifest.dataset(ds_key)
    arts = manifest.artifacts_of(ds_key)
    mirror = manifest.mirrors[arts[0].mirror] if arts else None
    card: dict[str, Any] = {
        "key": key,
        "name": prose["name"],
        "usedBy": prose["usedBy"],
        "variableKeys": prose.get("variableKeys") or variable_keys(manifest, ds_key),
        "role": prose["role"],
        "sourceName": (MIRROR_SOURCE_NAME.get(mirror.key, mirror.label) if mirror else ds.provider),
        "sourceUrl": mirror.url if mirror else ds.source_url,
        "license": licence_text(ds),
        "access": "account-required" if ds.terms and ds.terms.account else "public",
    }
    if arts:
        tars = [a for a in arts if a.kind == "tar"]
        card["size"] = prose.get("size") or ", ".join(
            f"{_size(a.bytes)} archive ({_size(a.disk_bytes)} extracted)" if a.kind == "tar"
            else f"{_size(a.bytes)} file" for a in arts)
        card["files"] = [{"name": a.name, "note": prose.get("fileNote", MIRROR_FILE_NOTE)} for a in arts]
        card["placeDir"] = place_dirs(ds, arts, prose.get("layout"))
        card["notes"] = list(prose.get("notes", [])) + ([MACOS_NOTE] if tars else [])
        if tars:
            card["extract"] = EXTRACT_CMD.format(name=tars[0].name)
        if any(a.available for a in arts):
            card["fetch"] = f"{FETCH_SCRIPT} {arts[0].name}"
    else:
        card["size"] = prose.get("size") or estimate_text(ds)
        card["files"] = list(prose.get("files", []))
        card["placeDir"] = place_dirs(ds, [], prose.get("layout"))
        card["notes"] = list(prose.get("notes", []))
    return card


def preset_card(manifest: Manifest, key: str, ds_key: str, prose: dict[str, Any]) -> dict[str, Any]:
    ds = manifest.dataset(ds_key)
    arts = manifest.artifacts_of(ds_key)
    card: dict[str, Any] = {
        "key": key,
        "name": prose["name"],
        "variableKeys": variable_keys(manifest, ds_key),
    }
    if prose.get("shipped"):
        card["shipped"] = True
    card["role"] = "Exposure values"
    card["artifact"] = prose.get("artifact") or " + ".join(a.name for a in arts)
    card["origin"] = prose["origin"]
    card["placeDir"] = place_dirs(ds, arts, None)
    mirrored = [a for a in arts if a.available]
    if mirrored and not prose.get("shipped"):
        art = mirrored[0]
        mirror = manifest.mirrors[art.mirror]
        card["downloadUrl"] = mirror.url
        card["downloadNote"] = (f"{art.name} ({_size(art.bytes)}) from the project's OneDrive folder "
                                f"(the same one as the boundary archives); drop it in {art.dest}/. "
                                f"{ds.license}. {ds.attribution}")
        card["fetchCmd"] = f"{FETCH_SCRIPT} {art.name}"
    return card


def generate(manifest: Manifest | None = None) -> dict[str, Any]:
    manifest = manifest or load_manifest()
    return {
        "selfServe": [self_serve_card(manifest, k, d, p) for k, d, p in SELF_SERVE],
        "preset": [preset_card(manifest, k, d, p) for k, d, p in PRESET],
    }


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when the committed file differs from the manifest")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    text = render(generate())
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != text:
            print(f"{args.output} is stale; run {Path(__file__).name} to regenerate", file=sys.stderr)
            return 1
        print(f"{args.output} is up to date")
        return 0
    args.output.write_text(text, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
