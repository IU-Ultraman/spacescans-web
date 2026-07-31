"""POST /api/data/upload-archive — allowlisted, checksum-verified upload.

The endpoint is reachable by any signed-up user (and on a public port in
Codespaces), so it accepts only the deployer's known distribution artifacts,
byte count and sha256 verified before anything is written into the data root.
These tests pin that contract, including the attacks an adversarial review
demonstrated against the first implementation (2026-07-31): a gzip bomb wrote
314 MB from a 306 KB body, and an arbitrary archive overwrote shipped files.
"""
import gzip
import hashlib
import io
import json
import os
import tarfile
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REAL_SECRET = "0" * 64  # not a placeholder — uploads refuse on those


def _get_client():
    tmp = tempfile.mkdtemp()
    data_root = Path(tempfile.mkdtemp())
    os.environ["DATA_DIR"] = tmp
    os.environ["DB_PATH"] = str(Path(tmp) / "test.db")
    os.environ["TASKS_DIR"] = str(Path(tmp) / "tasks")
    os.environ["SPACESCANS_DATA_DIR"] = str(data_root)
    os.environ["SECRET_KEY"] = _REAL_SECRET
    import importlib
    import app.config
    importlib.reload(app.config)
    import app.database
    importlib.reload(app.database)
    import app.auth
    importlib.reload(app.auth)
    import app.routers.auth
    importlib.reload(app.routers.auth)
    import app.routers.data_setup
    importlib.reload(app.routers.data_setup)
    import app.task_manager
    importlib.reload(app.task_manager)
    import app.routers.tasks
    importlib.reload(app.routers.tasks)
    import app.main
    importlib.reload(app.main)
    from app.main import create_app
    from app.database import init_db
    (Path(tmp) / "tasks").mkdir(parents=True, exist_ok=True)
    init_db()
    client = TestClient(create_app())
    resp = client.post("/api/auth/signup", json={
        "email": "u@u.com", "password": "pw123",
        "first_name": "U", "last_name": "U",
    })
    token = resp.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}, data_root


def _post(client, headers, filename, body):
    return client.post(
        f"/api/data/upload-archive?filename={filename}",
        content=body,
        headers={**headers, "Content-Type": "application/octet-stream"},
    )


def _tar_bytes(members: dict[str, bytes], transform=None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            if transform:
                transform(info)
            tar.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def _admit(monkeypatch, filename: str, body: bytes, *, kind="tar", dest=None,
           sha=None, size=None):
    """Point the manifest at a test artifact so a synthetic body is accepted."""
    import app.routers.data_setup as ds
    spec = {
        "sha256": sha or hashlib.sha256(body).hexdigest(),
        "bytes": size if size is not None else len(body),
        "kind": kind,
    }
    if dest:
        spec["dest"] = dest
    monkeypatch.setattr(ds, "_manifest", lambda: {filename: spec})


# --------------------------------------------------------------------------
# Happy paths
# --------------------------------------------------------------------------


def test_extracts_verified_archive_into_data_root(monkeypatch):
    client, headers, root = _get_client()
    body = _tar_bytes({
        "BG/C3/tiger2010_bg10_states/tl_2010_01_bg10/a.shp": b"shape",
        "BG/C3/tiger2024_bg_states/tl_2024_01_bg/b.shp": b"shape2",
    })
    _admit(monkeypatch, "bg_boundaries_v1.tar.gz", body)
    r = _post(client, headers, "bg_boundaries_v1.tar.gz", body)
    assert r.status_code == 200, r.text
    assert r.json()["extracted_files"] == 2
    assert r.json()["top_dirs"] == ["BG"]
    assert (root / "BG/C3/tiger2010_bg10_states/tl_2010_01_bg10/a.shp"
            ).read_bytes() == b"shape"
    assert not list((root / ".uploads").iterdir())  # temp copy cleaned up
    assert not list(root.rglob("*.part"))           # no leftover part files


def test_bare_rda_routes_to_its_dest(monkeypatch):
    client, headers, root = _get_client()
    body = b"RDX3\x00fake-rda-payload"
    name = "fara_nationwide_2010_2019_interpolated.Rda"
    _admit(monkeypatch, name, body, kind="bare", dest="FARA/C4")
    r = _post(client, headers, name, body)
    assert r.status_code == 200, r.text
    assert r.json()["placed"] == f"FARA/C4/{name}"
    assert (root / "FARA/C4" / name).read_bytes() == body


def test_real_manifest_lists_the_eight_distribution_artifacts():
    """The shipped manifest is the allowlist — keep it in sync with what the
    deployer actually publishes (same hashes as SHA256SUMS.txt)."""
    import app.routers.data_setup as ds
    m = json.loads(ds._MANIFEST_PATH.read_text())["artifacts"]
    assert len(m) == 8, sorted(m)
    assert "nhd_features_cache_v1.tar.gz" in m
    assert m["fara_nationwide_2010_2019_interpolated.Rda"]["kind"] == "bare"
    for name, spec in m.items():
        assert len(spec["sha256"]) == 64, name
        assert spec["bytes"] > 0, name
        assert spec["kind"] in ("tar", "bare"), name
        if spec["kind"] == "bare":
            assert spec.get("dest"), name
        else:
            # Measured, so the free-space precheck is exact rather than a
            # compression-ratio guess that could refuse a large archive.
            assert spec["extracted_bytes"] > 0, name


def test_no_artificial_size_ceiling_on_the_largest_archive():
    """A 38 GB archive must be acceptable wherever it fits — the only size
    rule is 'exactly the manifest's byte count'."""
    import app.routers.data_setup as ds
    nhd = json.loads(ds._MANIFEST_PATH.read_text())["artifacts"][
        "nhd_features_cache_v1.tar.gz"]
    assert nhd["bytes"] > 30 * 1000**3
    from app.config import settings
    # The legacy 100 MB request cap must not apply to this route.
    assert settings.MAX_UPLOAD_SIZE_MB * 1024**2 < nhd["bytes"]


def test_insufficient_storage_uses_measured_extracted_size(monkeypatch):
    client, headers, root = _get_client()
    import app.routers.data_setup as ds
    body = _tar_bytes({"Noise/C3/a.tif": b"x" * 1024})
    # Decimal GB throughout — that is what the message reports and what disk
    # tooling (df, the OneDrive listing) shows.
    spec = {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
            "kind": "tar", "extracted_bytes": 40 * 1000**3}
    monkeypatch.setattr(ds, "_manifest", lambda: {"noise_v1.tar.gz": spec})

    class _Usage:
        free = 5 * 1000**3

    monkeypatch.setattr(ds.shutil, "disk_usage", lambda _p: _Usage())
    r = _post(client, headers, "noise_v1.tar.gz", body)
    assert r.status_code == 507
    msg = r.json()["detail"]["message"]
    assert "40.0 GB extracted" in msg and "5.0 GB available" in msg
    assert not (root / "Noise").exists()


# --------------------------------------------------------------------------
# Allowlist + checksum: what makes extraction safe at all
# --------------------------------------------------------------------------


def test_rejects_unknown_filename():
    client, headers, root = _get_client()
    r = _post(client, headers, "totally_legit_v1.tar.gz",
              _tar_bytes({"FARA/C4/x": b"POISONED"}))
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "unknown_artifact"
    assert not (root / "FARA").exists()


def test_rejects_checksum_mismatch_without_extracting(monkeypatch):
    """Content poisoning: right filename, attacker payload. Reviewer's
    CRITICAL #2 — previously wrote POISONED over shipped files."""
    client, headers, root = _get_client()
    evil = _tar_bytes({
        "FARA/C4/fara_nationwide_2010_2019_interpolated.Rda": b"POISONED",
        "TEMIS/C3/temis_template.tif": b"POISONED",
    })
    _admit(monkeypatch, "noise_v1.tar.gz", evil,
           sha="a" * 64, size=len(evil))
    r = _post(client, headers, "noise_v1.tar.gz", evil)
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "checksum_mismatch"
    assert not (root / "FARA").exists()
    assert not (root / "TEMIS").exists()
    assert not list((root / ".uploads").iterdir())


def test_gzip_bomb_cannot_pass_the_hash_gate(monkeypatch):
    """Reviewer's CRITICAL #1: 306 KB body -> 314 MB written. A bomb's bytes
    cannot match a published digest, so it never reaches extraction."""
    client, headers, root = _get_client()
    bomb = _tar_bytes({"cache/C3/bomb.bin": b"\0" * (8 * 1024 * 1024)})
    _admit(monkeypatch, "noise_v1.tar.gz", bomb, sha="b" * 64, size=len(bomb))
    r = _post(client, headers, "noise_v1.tar.gz", bomb)
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "checksum_mismatch"
    assert not (root / "cache").exists()


def test_rejects_wrong_declared_size(monkeypatch):
    client, headers, _ = _get_client()
    body = _tar_bytes({"Noise/C3/a.tif": b"x"})
    _admit(monkeypatch, "noise_v1.tar.gz", body, size=len(body) + 999)
    r = _post(client, headers, "noise_v1.tar.gz", body)
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "size_mismatch"


def test_requires_content_length(monkeypatch):
    """Reviewer HIGH: a chunked body skipped every size guard."""
    client, headers, root = _get_client()
    body = _tar_bytes({"Noise/C3/a.tif": b"x"})
    _admit(monkeypatch, "noise_v1.tar.gz", body)

    def chunks():
        yield body  # httpx sends an iterator body as chunked

    r = client.post("/api/data/upload-archive?filename=noise_v1.tar.gz",
                    content=chunks(), headers=headers)
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "length_required"
    assert not (root / "Noise").exists()


def test_forged_token_on_placeholder_secret_cannot_upload(monkeypatch):
    """Reviewer HIGH: with the placeholder SECRET_KEY anyone can mint a valid
    token (get_current_user does no DB lookup), which would turn this endpoint
    into an arbitrary-write primitive into the shared data root. Uploads must
    refuse to run at all on a placeholder key."""
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    client, _, root = _get_client()
    import app.routers.data_setup as ds
    placeholder = "change-me-in-production"
    monkeypatch.setattr(ds.settings, "SECRET_KEY", placeholder)
    forged = jwt.encode(
        {"sub": "1", "email": "attacker@evil.example",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        placeholder, algorithm=ds.settings.ALGORITHM,
    )
    body = _tar_bytes({"FARA/C4/x.Rda": b"FORGED"})
    _admit(monkeypatch, "noise_v1.tar.gz", body)
    r = _post(client, {"Authorization": f"Bearer {forged}"},
              "noise_v1.tar.gz", body)
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "insecure_deployment"
    assert not (root / "FARA").exists()


def test_requires_auth():
    client, _, _ = _get_client()
    r = client.post("/api/data/upload-archive?filename=noise_v1.tar.gz",
                    content=b"x")
    assert r.status_code in (401, 403)


# --------------------------------------------------------------------------
# Member-level validation: defense in depth behind the hash gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("member", [
    "BG/../../etc/evil.txt",
    "/etc/evil.txt",
    "NotADataset/x.txt",
])
def test_rejects_unsafe_members(monkeypatch, member):
    client, headers, root = _get_client()
    body = _tar_bytes({member: b"x"})
    _admit(monkeypatch, "noise_v1.tar.gz", body)  # hash matches on purpose
    r = _post(client, headers, "noise_v1.tar.gz", body)
    assert r.status_code == 400, r.text
    assert not (root.parent / "etc" / "evil.txt").exists()
    assert not (root / "NotADataset").exists()


def test_rejects_symlink_member(monkeypatch):
    client, headers, root = _get_client()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("Noise/C3/link.tif")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        info.size = 0
        tar.addfile(info)
    body = buf.getvalue()
    _admit(monkeypatch, "noise_v1.tar.gz", body)
    r = _post(client, headers, "noise_v1.tar.gz", body)
    assert r.status_code == 400
    assert "symlink" in r.json()["detail"]["message"]
    assert not (root / "Noise/C3/link.tif").exists()


def test_rejects_hardlink_member(monkeypatch):
    client, headers, root = _get_client()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("Noise/C3/hard.tif")
        info.type = tarfile.LNKTYPE
        info.linkname = "FARA/C4/varnameCountRemoved.csv"
        info.size = 0
        tar.addfile(info)
    body = buf.getvalue()
    _admit(monkeypatch, "noise_v1.tar.gz", body)
    r = _post(client, headers, "noise_v1.tar.gz", body)
    assert r.status_code == 400
    assert not (root / "Noise/C3/hard.tif").exists()


# --------------------------------------------------------------------------
# Malformed bodies
# --------------------------------------------------------------------------


def test_skips_macos_metadata_members(monkeypatch):
    """The archives were packed on macOS from files with extended attributes,
    so they carry a `._x` sidecar per `x` (plus stray .DS_Store files). BSD
    tar reabsorbs the sidecars; Python's tarfile (and GNU tar) would write
    them as junk — ~15k files for the NHD cache. They must be skipped and
    excluded from the reported count."""
    client, headers, root = _get_client()
    body = _tar_bytes({
        "County/C3/tl_2010_us_county10/tl_2010_us_county10.shp": b"real",
        "County/C3/tl_2010_us_county10/._tl_2010_us_county10.shp": b"applejunk",
        "County/C3/._tl_2010_us_county10": b"applejunk",
        "County/C3/.DS_Store": b"applejunk",
        "__MACOSX/County/C3/junk": b"applejunk",
    })
    _admit(monkeypatch, "county_boundaries_v1.tar.gz", body)
    r = _post(client, headers, "county_boundaries_v1.tar.gz", body)
    assert r.status_code == 200, r.text
    assert r.json()["extracted_files"] == 1
    assert r.json()["top_dirs"] == ["County"]
    assert (root / "County/C3/tl_2010_us_county10/tl_2010_us_county10.shp"
            ).read_bytes() == b"real"
    assert not list(root.rglob("._*"))
    assert not (root / "County/C3/.DS_Store").exists()
    assert not (root / "__MACOSX").exists()


def test_sweeps_orphaned_staging_files(monkeypatch):
    """A hard stop (container restart, OOM kill) mid-upload leaves a staging
    file no `finally` can clean, and it can be tens of GB. The next upload
    must reclaim it — safe because uploads are serialized, so any *.part
    present while the lock is held is abandoned."""
    client, headers, root = _get_client()
    uploads = root / ".uploads"
    uploads.mkdir()
    orphan = uploads / "nhd_features_cache_v1.tar.gz.deadbeef.part"
    orphan.write_bytes(b"x" * 4096)

    body = _tar_bytes({"Noise/C3/a.tif": b"x"})
    _admit(monkeypatch, "noise_v1.tar.gz", body)
    r = _post(client, headers, "noise_v1.tar.gz", body)
    assert r.status_code == 200, r.text
    assert not orphan.exists()
    assert not list(uploads.iterdir())


def test_truncated_archive_is_a_400_not_a_500(monkeypatch):
    """A cut-off .tar.gz raises EOFError/zlib.error, not tarfile.ReadError —
    the first implementation let that surface as an unhandled 500."""
    client, headers, root = _get_client()
    full = _tar_bytes({"Noise/C3/a.tif": b"y" * 4096})
    cut = full[: len(full) // 2]
    _admit(monkeypatch, "noise_v1.tar.gz", cut)  # hash of the truncated bytes
    r = _post(client, headers, "noise_v1.tar.gz", cut)
    assert r.status_code == 400, r.text
    assert not list((root / ".uploads").iterdir())


def test_non_gzip_body_is_rejected(monkeypatch):
    client, headers, _ = _get_client()
    body = b"not a tarball at all"
    _admit(monkeypatch, "county_boundaries_v1.tar.gz", body)
    r = _post(client, headers, "county_boundaries_v1.tar.gz", body)
    assert r.status_code == 400
