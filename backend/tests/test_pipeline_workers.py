"""SPACESCANS_PIPELINE_WORKERS reaches the run context only when the package takes it."""
from __future__ import annotations

import dataclasses

import pytest

from app import pipeline_workers


@dataclasses.dataclass(frozen=True)
class _Ctx:
    engine: dict | None = None


@pytest.fixture
def flags(monkeypatch):
    def set_flags(**f):
        monkeypatch.setattr("app.variable_registry._pipeline_flags", lambda: dict(f))
    return set_flags


def test_workers_go_into_the_engine_block_when_the_package_has_the_flag(flags):
    flags(workers=True)
    assert pipeline_workers.with_workers(_Ctx(), 4).engine == {"workers": 4}
    assert pipeline_workers.with_workers(_Ctx(engine={"threads": 2}), 3).engine == {
        "threads": 2, "workers": 3}


def test_a_package_without_the_flag_gets_the_context_unchanged(flags):
    flags(episode_grouping=True)                 # spacescans 0.3.0
    ctx = _Ctx()
    assert pipeline_workers.with_workers(ctx, 4) is ctx
    assert not pipeline_workers.supported()


def test_one_worker_leaves_the_context_unchanged(flags):
    flags(workers=True)
    ctx = _Ctx()
    assert pipeline_workers.with_workers(ctx, 1) is ctx


def test_the_setting_defaults_to_four_and_refuses_zero(monkeypatch):
    from pydantic import ValidationError

    from app.config import Settings

    monkeypatch.delenv("SPACESCANS_PIPELINE_WORKERS", raising=False)
    assert Settings(_env_file=None).SPACESCANS_PIPELINE_WORKERS == 4
    monkeypatch.setenv("SPACESCANS_PIPELINE_WORKERS", "2")
    assert Settings(_env_file=None).SPACESCANS_PIPELINE_WORKERS == 2
    monkeypatch.setenv("SPACESCANS_PIPELINE_WORKERS", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_the_installed_package_and_the_helper_agree():
    """With the package's real flags: 0.3.0 leaves the context alone, 0.3.1 sets workers."""
    from spacescans.orchestrate import RunContext

    ctx = RunContext(run_dir="/r", cohort_parquet="/r/input.parquet", data_dir="/d")
    out = pipeline_workers.with_workers(ctx, 4)
    if pipeline_workers.supported():
        assert out.engine == {"workers": 4}
    else:
        assert out is ctx
