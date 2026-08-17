#!/usr/bin/env python
"""Build a feature_labels.csv for a workshop dataset that script 1 did not produce.

Script 1 writes feature_labels.csv itself when it reads a SPACESCANS run. The
pre-linked 100k dataset predates the web app — it came from the earlier
per-source parquet pipeline — so its labels have to be assembled from the same
two sources the app uses:

  * app/data/feature_dictionary.json  — the exposures the app links today
  * pipeline-data/FARA/C4/varnameCountRemoved.csv — the full USDA FARA label
    set, of which the app emits only four headline columns

Usage:
    python scripts/make_workshop_feature_labels.py <manifest.csv> <out.csv>

The manifest is the exposure_variable_manifest.csv beside the dataset; its
`variable` column carries the cleaned, prefixed names the R pipeline produced.
"""
import csv
import json
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_DICT = _BACKEND / "app" / "data" / "feature_dictionary.json"
_FARA_LABELS = (
    _BACKEND.parent / "pipeline-data" / "FARA" / "C4" / "varnameCountRemoved.csv"
)

# Prefix each source's columns carry in the merged data (see spacescans_specs
# in script 1, plus the three sources the workshop no longer links).
_PREFIX = {
    "zbp_primary_cbp_fallback": "soc_",
    "noise_270m": "",
    "tiger_road_proximity": "road_",
    "block_group_ndi": "",
    "block_group_walkability": "",
    "tract_fara_food_access": "fara_",
    "nhd_blue_space_proximity": "nhd_",
    "temis_uv": "temis_",
    "visible_nighttime_light": "vnl_",
}


def clean_name_one(x: str) -> str:
    """The R pipeline's snake_case rule, reproduced exactly."""
    x = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", x)
    x = re.sub(r"[^A-Za-z0-9]+", "_", x)
    x = re.sub(r"_+", "_", x)
    x = re.sub(r"^_|_$", "", x)
    return x.lower()


def build_index() -> dict[str, tuple[str, str]]:
    """final column name -> (label, detailed description)."""
    index: dict[str, tuple[str, str]] = {}

    features = json.loads(_DICT.read_text())["features"]
    for raw, spec in features.items():
        for prefix in set(_PREFIX.values()):
            index[prefix + clean_name_one(raw)] = (
                spec["label"], spec["definition"]
            )

    # The FARA panel carries 44 columns; the app links four of them, so the
    # rest are described only here.
    if _FARA_LABELS.exists():
        with _FARA_LABELS.open() as f:
            for row in csv.DictReader(f):
                name = "fara_" + clean_name_one(row["var"])
                index[name] = (row["label"], row["label"])

    # The parquet-era pipeline suffixed area-weighted grid measures with _aw;
    # the app writes the same measures without it. Same variable, same text.
    for name in list(index):
        index.setdefault(name + "_aw", index[name])

    return index


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    manifest_path, out_path = Path(argv[1]), Path(argv[2])

    index = build_index()
    rows, missing = [], []
    with manifest_path.open() as f:
        for entry in csv.DictReader(f):
            var = entry["variable"]
            hit = index.get(var)
            if hit is None:
                missing.append(var)
                rows.append({"varname": var, "label": var, "description": var})
            else:
                rows.append(
                    {"varname": var, "label": hit[0], "description": hit[1]}
                )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=("varname", "label", "description"), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} variables -> {out_path}")
    if missing:
        print(f"  no description for {len(missing)}: {', '.join(missing)}")
        print("  (these fall back to the variable name)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
