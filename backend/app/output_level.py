"""Output level of a task: one row per participant (the default) or one per location episode.

Phase D (PHASE_D.md section 2.2). A task's ``config.json`` carries ``"output_level"``:

* ``"participant"`` (the web app's default): ``result.csv`` has one row per participant id of
  the cohort, in order of first appearance, with ``pid`` and then the variables; no
  coordinates, dates or episode ids. A participant with no contributing day gets missing
  values. For participant ``i`` and variable ``v`` the value is the mean of the episode
  estimates over the participant's location episodes and source periods with a defined
  estimate, each weighted by its overlapping days. The package computes it in C4
  (``time.output_grouping: patient``); this module only asks for it and joins the result.
* ``"episode"``: one row per input row, the cohort's columns plus the variables, exactly as
  before phase D.

A ``config.json`` without the key was written before phase D (a task configured on the old
app, or a hand-written config such as the paper's scripts use): it runs per episode
(:data:`LEGACY_LEVEL`), so those runs stay byte-identical. Every config the app saves carries
the key (:data:`DEFAULT_LEVEL` when the client sends none).

The merge writes ``output/result_meta.json`` next to ``result.csv``; its ``output_level`` is the
level of the table the results endpoints read. A result without it predates phase D and is per
episode.

Package seam
    The level reaches the C4 render through the installed ``spacescans``: a ``RunContext`` field
    or a ``run_source`` keyword named ``output_level`` (``"participant"``/``"episode"``) or
    ``output_grouping`` (``"patient"``/``"episode"``), whichever the package has
    (:func:`package_support`). With neither, episode runs go on exactly as before and a
    participant run fails with :class:`ParticipantLevelUnsupported`. :func:`check_rendered`
    renders the plan's C4 steps (pure) and refuses a context that did not reach the YAML, and
    the participant merge refuses a C4 output with more than one row per participant.

Participant ids
    The web's cohort conversion keeps 0.2.7's ``pid_as_str=False`` (the legacy cache keys hash
    ``input.parquet``), so a numeric id is read as a number there. The C4 output's ids are
    mapped back to the cohort's own spelling row by row through ``input.parquet`` (row ``k`` of
    ``input.parquet`` is row ``k`` of ``input.csv``). Two different ids that read as the same
    number (such as ``007`` and ``7``) are one participant to the pipeline: the merge refuses
    that cohort at participant level rather than give both the pooled value.

Nothing here logs or returns a cohort value (an id, a date, a coordinate): messages carry
counts, step names and file names only.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import math
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PARTICIPANT = "participant"
EPISODE = "episode"
LEVELS: tuple[str, str] = (PARTICIPANT, EPISODE)
#: The level of a task whose client sent none (PUT /api/tasks/{id}/config, task_manager.save_config).
DEFAULT_LEVEL = PARTICIPANT
#: The level of a config.json or a result that does not record one: written before phase D.
LEGACY_LEVEL = EPISODE
#: The task config key.
CONFIG_KEY = "output_level"
#: The file next to result.csv that records the level of the table.
RESULT_META = "result_meta.json"
#: What one row of the output table is, for labels.
ROW_UNIT = {PARTICIPANT: "participants", EPISODE: "episodes"}
#: The values the package's two possible parameter names take for each level.
_PARAM_VALUES = {
    "output_level": {PARTICIPANT: "participant", EPISODE: "episode"},
    "output_grouping": {PARTICIPANT: "patient", EPISODE: "episode"},
}
#: The C4 YAML's ``time.output_grouping`` for each level.
GROUPING = _PARAM_VALUES["output_grouping"]
#: The cohort columns the output table never carries at participant level.
_ID_COLUMNS = ("pid", "PATID")


class OutputLevelError(ValueError):
    """A level that is not ``participant`` or ``episode``, or a table that does not fit one."""


class ParticipantLevelUnsupported(RuntimeError):
    """The installed spacescans cannot render participant-level (per participant) C4 output."""


# ---------------------------------------------------------------------------
# the level of a config and of a result
# ---------------------------------------------------------------------------

def normalize(value: Any, *, default: str = DEFAULT_LEVEL) -> str:
    """``participant`` or ``episode`` (case and surrounding blanks ignored); ``default`` for None."""
    if value is None:
        return default
    if isinstance(value, str) and value.strip().lower() in LEVELS:
        return value.strip().lower()
    raise OutputLevelError(
        f"output_level must be {LEVELS[0]!r} or {LEVELS[1]!r}, got {value!r}"
    )


def of_config(config: Mapping[str, Any]) -> str:
    """The level a task config asks for; a config without the key predates phase D (episode)."""
    return normalize(config.get(CONFIG_KEY), default=LEGACY_LEVEL)


def of_task(task_dir: Path) -> str:
    """The level a task's ``config.json`` asks for; no config (or no key) means episode."""
    path = Path(task_dir) / "config.json"
    if not path.is_file():
        return LEGACY_LEVEL
    return of_config(json.loads(path.read_text()))


def _output_dir(task_dir: Path) -> Path:
    return Path(task_dir) / "output"


def read_result_meta(task_dir: Path) -> dict[str, Any] | None:
    """``output/result_meta.json`` as a dict, or None when absent or unreadable."""
    path = _output_dir(task_dir) / RESULT_META
    try:
        meta = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None


def result_level(task_dir: Path) -> str:
    """The level of the task's ``result.csv``: from its meta file, else episode (pre-phase D)."""
    meta = read_result_meta(task_dir)
    if meta is None:
        return LEGACY_LEVEL
    try:
        return normalize(meta.get(CONFIG_KEY), default=LEGACY_LEVEL)
    except OutputLevelError:
        return LEGACY_LEVEL


def write_result_meta(task_dir: Path, *, level: str, rows: int,
                      experiments: Sequence[str]) -> Path:
    """Write ``output/result_meta.json`` atomically (after result.csv)."""
    level = normalize(level)
    out = _output_dir(task_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        CONFIG_KEY: level,
        "row_unit": ROW_UNIT[level],
        "rows": int(rows),
        "id_column": "pid",
        "experiments": list(experiments),
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = out / (RESULT_META + ".tmp")
    tmp.write_text(json.dumps(meta, indent=2))
    os.replace(tmp, out / RESULT_META)
    return out / RESULT_META


def clear_result_meta(task_dir: Path) -> None:
    """Remove a previous run's meta before a new result.csv is written."""
    try:
        (_output_dir(task_dir) / RESULT_META).unlink()
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# package seam: where the installed spacescans takes the level
# ---------------------------------------------------------------------------

def _context_class() -> Any:
    from spacescans.orchestrate import RunContext

    return RunContext


def _run_source() -> Any:
    from spacescans.orchestrate import run_source

    return run_source


def _accepts(fn: Any, name: str) -> bool:
    try:
        return name in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def package_support() -> tuple[str, str] | None:
    """``("context", name)`` or ``("run_source", name)``: where the level goes; None if nowhere.

    ``name`` is ``output_level`` or ``output_grouping`` (checked in that order), a field of the
    package's ``RunContext`` dataclass first, then a keyword of ``run_source``.
    """
    ctx_cls = _context_class()
    fields = ({f.name for f in dataclasses.fields(ctx_cls)}
              if dataclasses.is_dataclass(ctx_cls) else set())
    for name in _PARAM_VALUES:
        if name in fields:
            return ("context", name)
    run_source = _run_source()
    for name in _PARAM_VALUES:
        if _accepts(run_source, name):
            return ("run_source", name)
    return None


def supports_participant() -> bool:
    """True when the installed spacescans can be asked for participant-level output."""
    try:
        return package_support() is not None
    except Exception:  # noqa: BLE001 - an import problem is reported where the run starts
        return False


def _unsupported_message() -> str:
    try:
        import spacescans

        version = getattr(spacescans, "__version__", "?")
    except Exception:  # noqa: BLE001
        version = "?"
    return (
        f"participant-level output needs a spacescans that renders it (the installed "
        f"spacescans {version} takes no output level); upgrade the pipeline, or choose "
        f"episode-level output for this task"
    )


def run_context(task_dir: Path, *, data_dir: Any, buffer_m: Any, raster_res_m: Any,
                overlay: Mapping[str, dict] | None, level: str) -> Any:
    """The web runner's ``RunContext.from_task_dir(...)`` carrying ``level`` when the package can.

    Episode level with a package that takes no level is exactly the pre-phase-D call. Raises
    :class:`ParticipantLevelUnsupported` for participant level on such a package.
    """
    level = normalize(level)
    ctx_cls = _context_class()
    ctx = ctx_cls.from_task_dir(task_dir, data_dir=data_dir, buffer_m=buffer_m,
                                raster_res_m=raster_res_m, overlay=overlay)
    where = package_support()
    if where is None:
        if level != EPISODE:
            raise ParticipantLevelUnsupported(_unsupported_message())
        return ctx
    kind, name = where
    if kind == "context":
        ctx = dataclasses.replace(ctx, **{name: _PARAM_VALUES[name][level]})
    return ctx


def source_kwargs(level: str) -> dict[str, Any]:
    """Extra ``run_source`` keywords for ``level`` (empty unless the package takes it there)."""
    level = normalize(level)
    where = package_support()
    if where is None:
        if level != EPISODE:
            raise ParticipantLevelUnsupported(_unsupported_message())
        return {}
    kind, name = where
    return {name: _PARAM_VALUES[name][level]} if kind == "run_source" else {}


def check_rendered(steps: Sequence[Any], ctx: Any, level: str) -> str | None:
    """None when every C4 step whose YAML has a time block renders ``level``'s grouping.

    Otherwise the name of the first step that does not (the context did not reach the
    render). Rendering is pure; a step that cannot be rendered here is skipped (the run
    reports its render error itself). Only meaningful when the level goes through the
    context; with ``run_source`` keywords the package renders it inside the run.
    """
    want = GROUPING[normalize(level)]
    try:
        from spacescans.orchestrate.render import render
    except Exception:  # noqa: BLE001
        return None
    for step in steps:
        if getattr(step, "is_c3", False):
            continue
        try:
            cfg = render(step, ctx)
        except Exception:  # noqa: BLE001 - the run reports a render failure itself
            continue
        time_block = cfg.get("time") if isinstance(cfg, Mapping) else None
        if isinstance(time_block, Mapping) and time_block.get("output_grouping") != want:
            return str(getattr(step, "name", "?"))
    return None


# ---------------------------------------------------------------------------
# participant ids
# ---------------------------------------------------------------------------

def _canon(value: Any) -> str | None:
    """One spelling of an id value for matching: integral numbers without a decimal part."""
    if value is None:
        return None
    try:
        import numpy as np

        if isinstance(value, np.generic):
            value = value.item()
    except ImportError:  # pragma: no cover
        pass
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return None
        return str(int(value)) if value.is_integer() else repr(value)
    text = str(value)
    return text


def _cohort_ids(task_dir: Path) -> "Any":
    """The cohort's id column from ``input.csv`` as text (``pid``, or a legacy ``PATID``)."""
    import pandas as pd

    path = Path(task_dir) / "input.csv"
    header = pd.read_csv(path, nrows=0).columns.tolist()
    id_col = next((c for c in _ID_COLUMNS if c in header), None)
    if id_col is None:
        raise OutputLevelError("input.csv has no pid column")
    return pd.read_csv(path, dtype=str, usecols=[id_col])[id_col]


def participants(task_dir: Path) -> "Any":
    """``DataFrame[pid]``: every participant id of the cohort once, in first-appearance order."""
    import pandas as pd

    ids = _cohort_ids(task_dir)
    return pd.DataFrame({"pid": ids}).drop_duplicates(keep="first").reset_index(drop=True)


def id_lookup(task_dir: Path) -> dict[str, Any]:
    """C4 id (canonical spelling, as the pipeline read it) -> the cohort's own id text.

    Built row by row from ``input.parquet`` (what the pipeline read) and ``input.csv`` (what
    the user wrote). Raises :class:`OutputLevelError` when two different ids of the cohort are
    one id to the pipeline.
    """
    import pandas as pd

    texts = _cohort_ids(task_dir).tolist()
    parquet = Path(task_dir) / "input.parquet"
    import pyarrow.parquet as pq

    names = pq.read_schema(parquet).names
    id_col = next((c for c in _ID_COLUMNS if c in names), None)
    if id_col is None:
        raise OutputLevelError("input.parquet has no pid column")
    read = pd.read_parquet(parquet, columns=[id_col])[id_col].tolist()
    if len(read) != len(texts):
        raise OutputLevelError(
            f"input.parquet has {len(read)} rows for {len(texts)} rows of input.csv; "
            "rerun the task"
        )
    lookup: dict[str, Any] = {}
    collisions = 0
    for value, text in zip(read, texts):
        key = _canon(value)
        if key is None:
            continue
        if key in lookup and lookup[key] != text:
            collisions += 1
            continue
        lookup.setdefault(key, text)
    if collisions:
        raise OutputLevelError(
            f"participant-level output: {collisions} row(s) carry a participant id that is "
            "a different spelling of another participant's id once read as a number (for "
            "example leading zeros), so the pipeline would pool them; make the ids distinct "
            "text (for example prefix them with a letter) or choose episode-level output"
        )
    return lookup


# ---------------------------------------------------------------------------
# participant-level partial (one source) and fan-in (all sources)
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class ParticipantStats:
    """How many of the cohort's participants got at least one value from one source."""

    experiment: str
    cohort_n: int
    matched_n: int
    match_pct: float

    @property
    def low(self) -> bool:
        from spacescans.orchestrate.merge import LOW_MATCH_PCT

        return self.match_pct < LOW_MATCH_PCT

    def as_log_fields(self) -> dict[str, Any]:
        from spacescans.orchestrate.merge import LOW_MATCH_EVENT

        return {"experiment_key": self.experiment, "event": LOW_MATCH_EVENT,
                "match_pct": self.match_pct, "cohort_n": self.cohort_n,
                "matched_n": self.matched_n, CONFIG_KEY: PARTICIPANT}


def participant_partial(task_dir: Path, experiment: str, variables: Sequence[str],
                        parquet_map: Mapping[str, str], value_cols: Mapping[str, Sequence[str]],
                        *, renames: Mapping[str, str] | None = None,
                        rewrite_in_place: bool = False) -> tuple[Any, ParticipantStats]:
    """One source's participant-level partial: ``pid`` + its value columns, one row per participant.

    The participant counterpart of ``spacescans.orchestrate.merge.partial_from_dir``, with the
    same rules: ``renames`` applied first (written back into the C4 parquet with
    ``rewrite_in_place``, as for FAQSD), only the variable's value columns that are present
    kept, variables outer-merged in request order, the first variable winning a repeated
    column. Each C4 output must have one row per participant (``PATID`` or ``pid``).
    """
    import pandas as pd

    task_dir = Path(task_dir)
    out_dir = _output_dir(task_dir)
    lookup = id_lookup(task_dir)
    merged: pd.DataFrame | None = None
    for var_key in variables:
        path = out_dir / parquet_map[var_key]
        df = pd.read_parquet(path)
        if renames:
            df = df.rename(columns=dict(renames))
            if rewrite_in_place:
                df.to_parquet(path, index=False)
        id_col = next((c for c in ("PATID", "pid") if c in df.columns), None)
        if id_col is None:
            raise OutputLevelError(f"{path.name} has no participant id column (PATID)")
        if df[id_col].duplicated().any():
            raise OutputLevelError(
                f"participant-level output: {path.name} has more than one row per participant "
                f"(the installed spacescans did not apply participant level to {experiment}); "
                "choose episode-level output or upgrade the pipeline"
            )
        keep = [c for c in value_cols[var_key] if c in df.columns]
        part = df[[id_col] + keep].rename(columns={id_col: "pid"})
        part["pid"] = [lookup.get(_canon(v)) for v in part["pid"].tolist()]
        if part["pid"].isna().any():
            raise OutputLevelError(
                f"participant-level output: {path.name} names participant(s) that are not in "
                "the cohort"
            )
        if merged is None:
            merged = part
        else:
            new_cols = [c for c in part.columns if c == "pid" or c not in merged.columns]
            merged = merged.merge(part[new_cols], on="pid", how="outer")
    cohort = participants(task_dir)
    if merged is None:
        merged = cohort.copy()
    value_only = merged.drop(columns=["pid"])
    if value_only.shape[1] == 0:
        matched = len(cohort)
        pct = 100.0
    else:
        with_value = set(merged.loc[value_only.notna().any(axis=1), "pid"].tolist())
        matched = int(cohort["pid"].isin(with_value).sum())
        pct = round(100.0 * matched / max(len(cohort), 1), 2)
    return merged, ParticipantStats(experiment=experiment, cohort_n=len(cohort),
                                    matched_n=matched, match_pct=pct)


def participant_fan_in(task_dir: Path, experiment_keys: Sequence[str]) -> Any:
    """``result.csv`` at participant level: the cohort's participants, left-joined to each partial.

    Rows: every participant id of ``input.csv`` once, in first-appearance order (with no
    contributing day the values are missing). Columns: ``pid``, then each source's columns in
    the given order; a column whose name is already taken gets ``_<source>_dup`` (the
    episode-level fan-in's rule). Partials are read as text, so values reach result.csv as
    the partials wrote them.
    """
    import pandas as pd

    from spacescans.orchestrate.merge import partial_csv_name

    df = participants(task_dir)
    for exp_key in experiment_keys:
        partial = pd.read_csv(_output_dir(task_dir) / partial_csv_name(exp_key), dtype=str)
        if "pid" not in partial.columns:
            raise OutputLevelError(f"{partial_csv_name(exp_key)} has no pid column")
        df = df.merge(partial, on="pid", how="left", suffixes=("", f"_{exp_key}_dup"))
    return df


# ---------------------------------------------------------------------------
# what the results endpoints add
# ---------------------------------------------------------------------------

def linkage_rates(df: Any, exposure_columns: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Per exposure column: rows with a value, rows, and their share in percent (2 dp)."""
    total = int(len(df))
    out: dict[str, dict[str, Any]] = {}
    for col in exposure_columns:
        linked = int(df[col].notna().sum())
        out[col] = {"linked": linked, "total": total,
                    "rate_pct": round(100.0 * linked / total, 2) if total else 0.0}
    return out


def participant_states(task_dir: Path) -> Any:
    """``DataFrame[pid, state_fips]``: each participant placed in the state of their longest episode.

    The longest episode has the most days (end and start inclusive); ties go to the most recent
    start, then to the earlier row. An episode whose dates are blank or unreadable ranks below
    every dated one. A participant whose chosen episode has no ``state_fips`` is not placed.
    Returns None when the cohort has no ``state_fips`` column (no map, as before phase D).
    """
    import pandas as pd

    from app import cohort_dates

    path = Path(task_dir) / "input.csv"
    header = pd.read_csv(path, nrows=0).columns.tolist()
    if "state_fips" not in header:
        return None
    id_col = next((c for c in _ID_COLUMNS if c in header), None)
    if id_col is None:
        raise OutputLevelError("input.csv has no pid column")
    cols = [id_col, "state_fips"] + [c for c in ("startDate", "endDate") if c in header]
    df = pd.read_csv(path, dtype=str, usecols=cols)
    df = df.rename(columns={id_col: "pid"})
    try:
        cohort_dates.parse_date_columns(df)
    except ValueError:
        df["startDate"] = pd.NaT
        df["endDate"] = pd.NaT
    for c in ("startDate", "endDate"):
        if c not in df.columns:
            df[c] = pd.NaT
    days = (df["endDate"] - df["startDate"]).dt.days + 1
    df["_days"] = days.where(days.notna(), -1).clip(lower=-1).astype("int64")
    # A missing start sorts as the oldest possible start.
    df["_start"] = df["startDate"].fillna(pd.Timestamp.min)
    df["_row"] = range(len(df))
    ranked = df.sort_values(["pid", "_days", "_start", "_row"],
                            ascending=[True, False, False, True], kind="mergesort")
    chosen = ranked.drop_duplicates(subset=["pid"], keep="first")
    out = chosen[["pid", "state_fips"]].copy()
    out = out[out["state_fips"].notna() & (out["state_fips"].str.strip() != "")]
    out["state_fips"] = out["state_fips"].str.strip().str.zfill(2)
    return out.reset_index(drop=True)
