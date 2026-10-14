"""Commands the docs give for the backend container name its interpreter in full.

The backend image's PATH (micromamba base) has no /opt/conda/bin: only the image's
entrypoint activates the conda environment, and ``docker compose exec`` /
``docker exec`` bypass the entrypoint. A bare ``python`` (or ``spacescans``) there
fails with "executable file not found in $PATH"; the paper's scripts use
``/opt/conda/bin/python`` for the same reason.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = ("README.md", "DOCKER.md", "docs/cutover.md", "scripts/fetch_distribution.sh")
# `docker compose exec [-T] backend <cmd>` or `docker exec [-i] spacescans-web-backend-1 <cmd>`
# with a command the image's PATH cannot find.
BARE = re.compile(r"\bexec\s+(?:-[iT]+\s+)*(?:backend|spacescans-web-backend-1)\s+(?:python3?|spacescans|pip)\b")


@pytest.mark.parametrize("rel", DOCS)
def test_container_commands_use_the_full_interpreter_path(rel: str) -> None:
    path = REPO_ROOT / rel
    if not path.is_file():
        pytest.skip(f"{rel} is not in this checkout (the image holds only backend/)")
    bad = [f"{rel}:{n}: {line.strip()}"
           for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
           if BARE.search(line)]
    assert not bad, ("use /opt/conda/bin/python: the backend image's PATH has no /opt/conda/bin "
                     "outside its entrypoint, so exec cannot find a bare command:\n" + "\n".join(bad))


def test_the_pattern_catches_a_bare_interpreter() -> None:
    assert BARE.search("docker compose exec backend python -m spacescans data status")
    assert BARE.search("docker compose exec -T backend python -c 'print(1)'")
    assert BARE.search("docker exec -i spacescans-web-backend-1 spacescans --help")
    assert not BARE.search("docker compose exec backend /opt/conda/bin/python -m spacescans data status")
    assert not BARE.search("docker compose exec -T backend cat /proc/1/comm")
