"""Archive upload + auto-extract for the Data Setup page.

POST /api/data/upload-archive?filename=<name> streams one of the deployer's
distribution artifacts to a temp file under the data root, verifies it, then
places it where the pipeline reads it — the browser equivalent of
`tar -xzf <archive> -C pipeline-data/`.

Security model — the endpoint is reachable by any signed-up user, and in
Codespaces deployments on a public port, so it accepts NOTHING but the known
artifacts:

  1. `filename` must be in app/data/distribution_manifest.json.
  2. Content-Length must be present and exactly the manifest's byte count.
  3. The stream is capped at that count (a longer body is cut off and rejected).
  4. sha256 of the received bytes must equal the manifest's — checked BEFORE
     anything is extracted.

Only after (1)-(4) is the archive opened. That is what makes extraction safe:
a decompression bomb, a traversal member or poisoned content cannot survive a
hash match against a published digest. Member-level validation (no absolute
paths, no `..`, regular files/dirs only, known top-level dataset dir) stays as
defense in depth, and members are written to `.part` + os.replace so a
concurrent pipeline run never observes a half-written file.

Uploads are serialized (one at a time, 409 otherwise): the work is disk-bound,
and concurrency only multiplies the ways a shared data root can be corrupted.
"""
import asyncio
import gzip
import hashlib
import json
import logging
import os
import shutil
import tarfile
import tempfile
import zlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from app.auth import get_current_user
from app.config import settings, _DATASET_DIRS

router = APIRouter(prefix="/api/data", tags=["data"])
_log = logging.getLogger(__name__)

_CHUNK = 4 * 1024 * 1024
_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "distribution_manifest.json"
# Disk-bound work; also keeps two uploads from racing on the same dataset dir.
_upload_lock = asyncio.Lock()
_PLACEHOLDER_SECRETS = {"change-me-in-production", "change-me-to-a-real-secret"}


def _manifest() -> dict[str, dict]:
    return json.loads(_MANIFEST_PATH.read_text())["artifacts"]


def _bad(message: str, error: str = "unsafe_or_invalid_archive") -> HTTPException:
    return HTTPException(status_code=400, detail={"error": error, "message": message})


def _validate_member(m: tarfile.TarInfo, root: Path) -> None:
    p = Path(m.name)
    if not p.parts:
        raise _bad("empty member name in archive")
    if p.is_absolute() or ".." in p.parts:
        raise _bad(f"unsafe path in archive: {m.name!r}")
    if p.parts[0] not in _DATASET_DIRS:
        raise _bad(
            f"archive entry {m.name!r} is outside the known dataset dirs "
            f"({', '.join(sorted(_DATASET_DIRS))})"
        )
    if not (m.isreg() or m.isdir()):
        raise _bad(
            f"archive entry {m.name!r} is not a regular file or directory "
            "(symlinks/hardlinks/devices are not allowed)"
        )
    if not (root / p).resolve().is_relative_to(root.resolve()):
        raise _bad(f"archive entry escapes the data root: {m.name!r}")


def _extract_tar(archive: Path, root: Path) -> tuple[int, set[str]]:
    """Validate then write each member. Files land via `.part` + os.replace so
    a reader (e.g. a running pipeline step) never sees a partial file."""
    count = 0
    tops: set[str] = set()
    with tarfile.open(archive, "r:gz") as tar:
        for m in tar:
            _validate_member(m, root)
            tops.add(Path(m.name).parts[0])
            target = root / m.name
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if target.is_dir():
                raise _bad(
                    f"archive entry {m.name!r} collides with an existing directory"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(m)
            if src is None:  # pragma: no cover - isreg() implies extractable
                raise _bad(f"unreadable archive entry: {m.name!r}")
            part = target.with_name(target.name + ".part")
            try:
                with src, open(part, "wb") as dst:
                    shutil.copyfileobj(src, dst, _CHUNK)
                os.replace(part, target)
            finally:
                part.unlink(missing_ok=True)
            count += 1
    return count, tops


def _write_stream_sync(fh, chunk: bytes, digest) -> None:
    fh.write(chunk)
    digest.update(chunk)


@router.post("/upload-archive")
async def upload_archive(
    request: Request,
    filename: str = Query(..., max_length=128,
                          description="Distribution artifact filename"),
    user: dict = Depends(get_current_user),
):
    # A forgeable token would make this endpoint an arbitrary-write primitive
    # into the shared data root, so refuse to serve it on the placeholder key.
    if settings.SECRET_KEY in _PLACEHOLDER_SECRETS:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "insecure_deployment",
                "message": (
                    "uploads are disabled while SECRET_KEY is the placeholder "
                    "value — set a real one (openssl rand -hex 32) in .env and "
                    "restart"
                ),
            },
        )

    artifacts = _manifest()
    spec = artifacts.get(filename)
    if spec is None:
        raise _bad(
            f"{filename!r} is not one of the deployer's distribution artifacts "
            f"({', '.join(sorted(artifacts))})",
            error="unknown_artifact",
        )

    expected_bytes = int(spec["bytes"])
    length_header = request.headers.get("content-length")
    if length_header is None:
        raise _bad(
            "Content-Length is required (send the file as a plain body, not "
            "chunked)",
            error="length_required",
        )
    try:
        length = int(length_header)
    except ValueError:
        raise _bad(f"invalid Content-Length: {length_header!r}",
                   error="length_required") from None
    if length != expected_bytes:
        raise _bad(
            f"{filename} should be {expected_bytes:,} bytes but the upload "
            f"declares {length:,} — wrong or truncated file?",
            error="size_mismatch",
        )

    root = settings.SPACESCANS_DATA_DIR
    if not root.is_dir():
        raise HTTPException(
            status_code=500,
            detail={"error": "data_root_missing",
                    "message": f"data root not mounted: {root}"},
        )

    # The upload copy plus the extracted contents both land on this volume.
    need = int(expected_bytes * 2.5) if spec["kind"] == "tar" else expected_bytes
    free = shutil.disk_usage(root).free
    if free < need + 1024**3:
        raise HTTPException(
            status_code=507,
            detail={
                "error": "insufficient_storage",
                "message": (
                    f"need ~{need / 1e9:.1f} GB free on the data volume, have "
                    f"{free / 1e9:.1f} GB"
                ),
            },
        )

    if _upload_lock.locked():
        raise HTTPException(
            status_code=409,
            detail={"error": "upload_in_progress",
                    "message": "another upload is being processed — retry when it finishes"},
        )

    async with _upload_lock:
        uploads = root / ".uploads"
        uploads.mkdir(exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=uploads, prefix=f"{filename}.",
                                        suffix=".part")
        os.close(fd)
        tmp = Path(tmp_name)
        digest = hashlib.sha256()
        received = 0
        try:
            with open(tmp, "wb") as f:
                async for chunk in request.stream():
                    received += len(chunk)
                    if received > expected_bytes:
                        raise _bad(
                            f"upload exceeded the expected {expected_bytes:,} "
                            "bytes — aborted",
                            error="size_mismatch",
                        )
                    await run_in_threadpool(_write_stream_sync, f, chunk, digest)

            if received != expected_bytes:
                raise _bad(
                    f"upload ended after {received:,} of {expected_bytes:,} "
                    "bytes — connection interrupted?",
                    error="size_mismatch",
                )
            actual = digest.hexdigest()
            if actual != spec["sha256"]:
                raise _bad(
                    f"checksum mismatch for {filename} — the download is "
                    f"corrupt or not the distributed file (got {actual[:16]}…, "
                    f"expected {spec['sha256'][:16]}…). Re-download and retry.",
                    error="checksum_mismatch",
                )

            if spec["kind"] == "bare":
                dest_dir = root / spec["dest"]
                dest_dir.mkdir(parents=True, exist_ok=True)
                final = dest_dir / filename
                await run_in_threadpool(os.replace, tmp, final)
                _log.info("upload-archive: placed %s (%d bytes) for %s",
                          final, received, user["email"])
                return {"placed": f"{spec['dest']}/{filename}", "bytes": received}

            try:
                count, tops = await run_in_threadpool(_extract_tar, tmp, root)
            except HTTPException:
                raise
            except (tarfile.TarError, EOFError, zlib.error,
                    gzip.BadGzipFile) as e:
                raise _bad(f"could not read {filename} as a .tar.gz: {e}") from e
            except OSError as e:
                raise HTTPException(
                    status_code=507,
                    detail={"error": "extraction_failed",
                            "message": f"write failed while extracting: {e}"},
                ) from e
            _log.info("upload-archive: extracted %s -> %d files under %s for %s",
                      filename, count, sorted(tops), user["email"])
            return {"extracted_files": count, "top_dirs": sorted(tops),
                    "bytes": received}
        finally:
            tmp.unlink(missing_ok=True)
