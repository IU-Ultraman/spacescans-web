"""Single-experiment orchestrator stub: ZCTA5 × CBP community-organization density.

This stub exists so the variable_registry experiment whitelist accepts
``zcta5_cbp`` (referenced by ``cbp_zcta5`` in ``variable_metadata.json``).
Sprint 3 Task T7 fills in the run-time implementation; until then any
attempt to dispatch this experiment will fail at runtime with the
NotImplementedError below.

Spawned by ``app.task_manager.start_task`` as::

    python -m app.experiments.zcta5_cbp run <task_dir>
"""
from __future__ import annotations


def run(*_args, **_kwargs):  # pragma: no cover - filled in by T7
    raise NotImplementedError(
        "zcta5_cbp experiment runner is not implemented yet "
        "(scheduled for Sprint 3 Task T7)"
    )


if __name__ == "__main__":  # pragma: no cover
    run()
