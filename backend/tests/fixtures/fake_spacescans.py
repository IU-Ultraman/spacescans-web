#!/usr/bin/env python3
"""Tiny stand-in for the real `spacescans run` CLI used by unit tests.

Behaviour switches based on the second positional arg (the YAML path's
basename):
  - if filename contains "fail" -> exit 1 with an error line
  - if filename contains "hang" -> sleep forever (used for timeout tests)
  - otherwise -> emit 3 progress lines, write an empty parquet to the
    output.path declared in the YAML, exit 0.
"""
import sys
import time
from pathlib import Path

import yaml
import pandas as pd


def main():
    # sys.argv looks like: ['fake_spacescans.py', 'run', '--data-dir', ..., '<yaml>']
    yaml_path = Path(sys.argv[-1])
    if "fail" in yaml_path.name:
        print("[overlap_fast] tile 1/3 ( 33.3%)", flush=True)
        print("ERROR: something broke", file=sys.stderr, flush=True)
        sys.exit(1)
    if "hang" in yaml_path.name:
        while True:
            time.sleep(0.1)

    print("[overlap_fast] tile 1/3 ( 33.3%)", flush=True)
    print("[overlap_fast] tile 2/3 ( 66.7%)", flush=True)
    print("[overlap_fast] tile 3/3 (100.0%)", flush=True)
    cfg = yaml.safe_load(yaml_path.read_text())
    out_path = Path(cfg["output"]["path"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"PATID": ["P1"], "value": [0.0]}).to_parquet(out_path, index=False)
    sys.exit(0)


if __name__ == "__main__":
    main()
