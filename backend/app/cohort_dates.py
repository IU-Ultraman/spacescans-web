"""Cohort date parsing — the single place that decides how startDate/endDate
strings are read.

Why this exists: upload validation used pandas' flexible inference (which
happily accepts "8/19/2017") while the pipeline runners parsed with a strict
"%Y-%m-%d". A cohort could therefore pass upload and then fail mid-run with
`csv_to_parquet failed: ValueError('time data "8/19/2017" doesn't match
format "%Y-%m-%d"')`. Both paths now call in here, so what uploads is what runs.

Two rules keep the flexibility honest:

1. **Whole-column match, never per-element.** pandas' `format="mixed"` infers
   each value on its own, so one row can be read month-first and the next
   day-first. Here a candidate format must parse *every* value or it is
   rejected outright.
2. **One format across all date columns.** startDate and endDate are resolved
   together, so an episode can't get its start read US-style and its end
   read day-first.

Ambiguity: "3/4/2017" is 4 March under one convention and 3 April under the
other, and nothing in the data can settle it. Month-first is tried first —
these cohorts are US (Census FIPS, CONUS exposure grids), so "8/19/2017" is
19 August. Day-first is still attempted afterwards, so a non-US export like
"19/8/2017" parses instead of failing; it can only win when month-first is
impossible. The chosen format is logged whenever it isn't plain ISO.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

import pandas as pd

_log = logging.getLogger(__name__)

# Tried in order; the first format that parses every value across every date
# column wins. ISO first (the canonical form), then month-first US variants,
# then day-first as a fallback for non-US exports.
ACCEPTED_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",             # 2017-08-19  (canonical)
    "%Y-%m-%d %H:%M:%S",    # 2017-08-19 00:00:00
    "%m/%d/%Y",             # 8/19/2017   (US)
    "%m/%d/%y",             # 8/19/17
    "%m-%d-%Y",             # 8-19-2017
    "%Y/%m/%d",             # 2017/08/19
    "%d/%m/%Y",             # 19/8/2017   (day-first; only when month-first fails)
    "%d-%b-%Y",             # 19-Aug-2017
    "%b %d, %Y",            # Aug 19, 2017
)


def _clean(values: pd.Series) -> pd.Series:
    """Trimmed strings with blanks as NA (so empty cells stay NaT, not errors)."""
    s = values.astype("string").str.strip()
    return s.mask(s == "")


def detect_date_format(columns: Iterable[pd.Series]) -> str:
    """Return the one format that parses every non-empty value in `columns`.

    Raises ValueError naming a failing sample and the accepted formats.
    """
    non_null = [c.dropna() for c in (_clean(col) for col in columns)]
    non_null = [c for c in non_null if not c.empty]
    if not non_null:
        return ACCEPTED_DATE_FORMATS[0]  # nothing to go on; canonical is fine

    for fmt in ACCEPTED_DATE_FORMATS:
        try:
            for col in non_null:
                pd.to_datetime(col, format=fmt, errors="raise")
        except (ValueError, TypeError):
            continue
        return fmt

    sample = str(non_null[0].iloc[0])
    raise ValueError(
        f"Unrecognized date format: {sample!r}. Dates must use one consistent "
        f"format across startDate and endDate. Accepted: "
        f"{', '.join(ACCEPTED_DATE_FORMATS)}"
    )


def parse_date_columns(
    df: pd.DataFrame, columns: Sequence[str] = ("startDate", "endDate")
) -> pd.DataFrame:
    """Parse `columns` in-place to datetime64 using one shared format.

    Blank cells become NaT. Raises ValueError if no single format fits.
    """
    present = [c for c in columns if c in df.columns]
    if not present:
        return df

    fmt = detect_date_format(df[c] for c in present)
    if fmt != ACCEPTED_DATE_FORMATS[0]:
        _log.info(
            "cohort dates parsed with format %r (columns: %s)",
            fmt, ", ".join(present),
        )
    for c in present:
        df[c] = pd.to_datetime(_clean(df[c]), format=fmt, errors="coerce")
    return df
