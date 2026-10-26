"""How many worker processes a pipeline step may use (``SPACESCANS_PIPELINE_WORKERS``).

spacescans 0.3.1 and later take ``RunContext.engine["workers"]`` and write it into every
rendered config. The spatial computation of every source (0.3.2; the polygon-overlap weights
only in 0.3.1) and ACAG's NetCDF files are then computed by that many processes, with the
same output as one process. The
legacy-v1 weight cache keys do not read the rendered config, so cache hits are unchanged.
"""
from __future__ import annotations

import dataclasses
from typing import Any


def supported() -> bool:
    """True when the installed spacescans has the ``workers`` capability flag."""
    from app.variable_registry import _pipeline_flags

    return bool(_pipeline_flags().get("workers"))


def with_workers(ctx: Any, workers: int) -> Any:
    """``ctx`` with ``engine["workers"] = workers``; unchanged for one worker or a package
    without the flag (spacescans 0.3.0 refuses an unknown engine key)."""
    if workers <= 1 or not supported():
        return ctx
    return dataclasses.replace(ctx, engine={**(ctx.engine or {}), "workers": workers})
