#!/usr/bin/env python
"""Regenerate app/data/distribution_manifest.json from the built archives.

The manifest is the allowlist POST /api/data/upload-archive validates against
(filename + byte count + sha256), so it must be refreshed whenever the
distribution archives are rebuilt — otherwise browser uploads of the new
archives are rejected as checksum mismatches.

Usage (from backend/):
    python scripts/refresh_distribution_manifest.py /path/to/archive-dir

The archive dir is where the artifacts and their SHA256SUMS.txt live (the
files uploaded to the deployer's OneDrive folder). Hashes are recomputed from
the files themselves and cross-checked against SHA256SUMS.txt when present.
"""
import hashlib
import json
import sys
from pathlib import Path

_OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "distribution_manifest.json"
# Artifacts that are placed as-is rather than extracted, and where they go.
_BARE_DEST = {"fara_nationwide_2010_2019_interpolated.Rda": "FARA/C4"}
_COMMENT = (
    "Allowlist of deployer-distributed artifacts accepted by "
    "POST /api/data/upload-archive. An upload must match a filename here AND "
    "its sha256 before anything is extracted - that is what makes the "
    "endpoint safe to expose: no arbitrary archives, no decompression bombs, "
    "no content poisoning. These are the same hashes published as "
    "SHA256SUMS.txt alongside the archives. Regenerate with "
    "scripts/refresh_distribution_manifest.py when the archives change."
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    src = Path(argv[1])
    if not src.is_dir():
        print(f"not a directory: {src}")
        return 2

    published: dict[str, str] = {}
    sums = src / "SHA256SUMS.txt"
    if sums.exists():
        for line in sums.read_text().splitlines():
            parts = line.split()
            if len(parts) == 2:
                published[parts[1]] = parts[0]

    names = sorted(
        [p.name for p in src.glob("*.tar.gz")]
        + [n for n in _BARE_DEST if (src / n).exists()]
    )
    if not names:
        print(f"no artifacts found in {src}")
        return 1

    artifacts: dict[str, dict] = {}
    for name in names:
        path = src / name
        digest = sha256(path)
        if name in published and published[name] != digest:
            print(f"MISMATCH vs SHA256SUMS.txt: {name}")
            return 1
        spec = {"sha256": digest, "bytes": path.stat().st_size,
                "kind": "bare" if name in _BARE_DEST else "tar"}
        if name in _BARE_DEST:
            spec["dest"] = _BARE_DEST[name]
        artifacts[name] = spec
        print(f"  {name:45s} {spec['bytes']:>14,}  {digest[:16]}…")

    with open(_OUT, "w") as f:
        json.dump({"_comment": _COMMENT, "artifacts": artifacts}, f, indent=2)
        f.write("\n")
    print(f"wrote {_OUT} ({len(artifacts)} artifacts)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
