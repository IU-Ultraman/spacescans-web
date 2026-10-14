"""Archive upload + auto-extract for the Data Setup page.

POST /api/data/upload-archive?filename=<name> streams one of the deployer's
distribution artifacts to a temp file under the data root, verifies it, then
places it where the pipeline reads it — the browser equivalent of
`tar -xzf <archive> -C pipeline-data/`.

Security model — the endpoint is reachable by any signed-up user, and in
Codespaces deployments on a public port, so it accepts NOTHING but the known
artifacts:

  1. `filename` must be an artifact of the spacescans data manifest
     (spacescans/data/manifest.json: the same hashes as SHA256SUMS.txt).
  2. Content-Length must be present and exactly the manifest's byte count.
  3. The stream is capped at that count (a longer body is cut off and rejected).
  4. sha256 of the received bytes must equal the manifest's — checked BEFORE
     anything is extracted.

Only after (1)-(4) is the archive opened. That is what makes extraction safe:
a decompression bomb, a traversal member or poisoned content cannot survive a
hash match against a published digest. Member-level validation (no absolute
paths, no `..`, regular files/dirs only, known top-level dataset dir, and the
artifact's declared roots) stays as defense in depth, and members are written
to `.part` + os.replace so a concurrent pipeline run never observes a
half-written file. Extraction is ``spacescans.data.extract`` (the port of the
code that used to live here, with the same messages).

Uploads are serialized (one at a time, 409 otherwise): the work is disk-bound,
and concurrency only multiplies the ways a shared data root can be corrupted.
"""
import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from spacescans.data import MANIFEST_PATH, load_manifest
from spacescans.data.errors import DataCorruptError, UnsafeArchiveError
from spacescans.data.extract import extract_archive
from starlette.concurrency import run_in_threadpool

from app.auth import get_current_user
from app.config import settings

router = APIRouter(prefix="/api/data", tags=["data"])
_log = logging.getLogger(__name__)

# The package's data manifest: the allowlist this endpoint checks against.
_MANIFEST_PATH = MANIFEST_PATH
# Disk-bound work; also keeps two uploads from racing on the same dataset dir.
_upload_lock = asyncio.Lock()
_PLACEHOLDER_SECRETS = {"change-me-in-production", "change-me-to-a-real-secret"}


def _manifest() -> dict[str, dict]:
    """The distribution artifacts, from the spacescans data manifest.

    ``{filename: {"sha256", "bytes", "kind", "extracted_bytes" | "dest",
    "roots"}}``: every mirrored file (archives and bare files, whether or not
    it is on the mirror yet; the hash is what admits an upload).
    """
    out: dict[str, dict] = {}
    for name, art in load_manifest().artifacts.items():
        spec: dict = {"sha256": art.sha256, "bytes": art.bytes, "kind": art.kind}
        if art.kind == "tar":
            spec["extracted_bytes"] = int(art.extracted_bytes or 0)
            spec["roots"] = list(art.roots)
        else:
            spec["dest"] = art.dest
        out[name] = spec
    return out


def _bad(message: str, error: str = "unsafe_or_invalid_archive") -> HTTPException:
    return HTTPException(status_code=400, detail={"error": error, "message": message})


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

    # Peak usage = the upload copy + the extracted contents, both on this
    # volume. There is no artificial size ceiling: the 38 GB NHD archive is
    # fine anywhere it fits. `extracted_bytes` comes from the manifest (a
    # measured value, not a compression-ratio guess, which would falsely
    # refuse large archives on machines that can hold them).
    need = expected_bytes + int(spec.get("extracted_bytes") or 0)
    free = shutil.disk_usage(root).free
    if free < need + 1024**3:
        raise HTTPException(
            status_code=507,
            detail={
                "error": "insufficient_storage",
                "message": (
                    f"{filename} needs ~{need / 1e9:.1f} GB free on the data "
                    f"volume ({expected_bytes / 1e9:.1f} GB upload + "
                    f"{int(spec.get('extracted_bytes') or 0) / 1e9:.1f} GB "
                    f"extracted, plus 1 GB headroom) — only "
                    f"{free / 1e9:.1f} GB available"
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
        # Sweep orphaned staging files. A client disconnect unwinds through
        # the `finally` below, but a hard stop (container restart, OOM kill)
        # cannot — and an orphan here can be tens of GB. Uploads are
        # serialized by _upload_lock in this single-worker process, so while
        # we hold it any *.part present is by definition abandoned.
        for stale in uploads.glob("*.part"):
            try:
                size = stale.stat().st_size
                stale.unlink()
                _log.warning("upload-archive: removed orphaned staging file "
                             "%s (%d bytes)", stale.name, size)
            except OSError:  # pragma: no cover - racing removal is fine
                pass
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
                result = await run_in_threadpool(
                    extract_archive, tmp, root, allowed_roots=spec.get("roots"),
                    hash_files=False,
                )
            except UnsafeArchiveError as e:
                raise _bad(str(e)) from e
            except DataCorruptError as e:
                cause = e.__cause__ if e.__cause__ is not None else e
                raise _bad(f"could not read {filename} as a .tar.gz: {cause}") from e
            except OSError as e:
                raise HTTPException(
                    status_code=507,
                    detail={"error": "extraction_failed",
                            "message": f"write failed while extracting: {e}"},
                ) from e
            _log.info("upload-archive: extracted %s -> %d files under %s for %s",
                      filename, result.count, sorted(result.tops), user["email"])
            return {"extracted_files": result.count, "top_dirs": sorted(result.tops),
                    "bytes": received}
        finally:
            tmp.unlink(missing_ok=True)
