#!/usr/bin/env python3
"""Stand-in for ``spacescans run`` that honours the output level (phase D tests).

Like ``fake_spacescans.py`` it reads the rendered YAML (the last argument) and
writes a parquet to ``output.path``, but it emits the YAML's
``exposure.value_cols`` with known values, and its grouping is
``FAKE_SPACESCANS_GROUPING`` when set (the tests set it, standing in for a
package that renders ``time.output_grouping: patient``), else the YAML's
``time.output_grouping``, else ``episode``:

* episode: one row per input row, ``PATID`` = the parquet's pid and ``geoid`` =
  episode_id, value column j = (episode_id + 1) * (j + 1);
* patient: one row per distinct pid (first appearance), the mean of that
  participant's episode values, except that a pid listed (comma-separated) in
  ``FAKE_SPACESCANS_NO_VALUE`` gets no row at all, like a participant no day of
  whose episodes overlaps the source.

Values are synthetic; no cohort value is printed.
"""
import os
import sys
from pathlib import Path

import pandas as pd
import yaml


def main() -> int:
    yaml_path = Path(sys.argv[-1])
    cfg = yaml.safe_load(yaml_path.read_text())
    out_path = Path(cfg["output"]["path"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    grouping = (os.environ.get("FAKE_SPACESCANS_GROUPING")
                or (cfg.get("time") or {}).get("output_grouping") or "episode")
    value_cols = list(((cfg.get("exposure") or {}).get("value_cols")) or ["value"])
    patients = pd.read_parquet(cfg["buffer"]["patient_file"])
    episodes = pd.DataFrame({"PATID": patients["pid"].tolist(),
                             "geoid": patients["episode_id"].tolist()})
    for j, col in enumerate(value_cols):
        episodes[col] = (episodes["geoid"] + 1.0) * (j + 1)
    if grouping == "patient":
        skip = {s for s in os.environ.get("FAKE_SPACESCANS_NO_VALUE", "").split(",") if s}
        out = (episodes.drop(columns=["geoid"])
               .groupby("PATID", sort=False, dropna=False).mean().reset_index())
        if skip:
            out = out[~out["PATID"].astype(str).isin(skip)]
    else:
        out = episodes
    print("[fake] 1/1 (100.0%)", flush=True)
    out.to_parquet(out_path, index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
