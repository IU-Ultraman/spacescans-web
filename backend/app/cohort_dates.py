"""Cohort date parsing — the single place that decides how startDate/endDate
strings are read.

Why this exists: upload validation used pandas' flexible inference (which
happily accepts "8/19/2017") while the pipeline runners parsed with a strict
"%Y-%m-%d". A cohort could therefore pass upload and then fail mid-run with
`csv_to_parquet failed: ValueError('time data "8/19/2017" doesn't match
format "%Y-%m-%d"')`. Both paths now call in here, so what uploads is what runs.

Only two formats are accepted — ISO `2017-08-19` and US `8/19/2017`. The
earlier list also took `8/19/17`, `8-19-2017`, `2017/08/19`, `19-Aug-2017`
and `Aug 19, 2017`, which bought little: every one of those is a
re-export away from a supported form, while each extra candidate is another
way for a file to parse as a date nobody meant. Two-digit years and
day-first slashes are the sharp ones — `8/19/17` guesses a century, and
`19/8/2017` reads as 19 August under one convention and is invalid under the
other, so a cohort could shift by months depending on which format matched
first.

Two rules keep even that honest:

1. **Whole-column match, never per-element.** pandas' `format="mixed"` infers
   each value on its own, so one row can be read month-first and the next
   day-first. Here a candidate format must parse *every* value or it is
   rejected outright.
2. **One format across all date columns.** startDate and endDate are resolved
   together, so an episode can't get its start read one way and its end
   another.

Ambiguity that remains: "3/4/2017" is 4 March under the US convention and
3 April elsewhere, and nothing in the data settles it. These cohorts are US
(Census FIPS, CONUS exposure grids), so slash dates are read month-first —
and since day-first is no longer accepted, a non-US export like "19/8/2017"
is now rejected outright rather than silently reinterpreted. The chosen
format is logged whenever it isn't plain ISO.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

import pandas as pd

_log = logging.getLogger(__name__)

# Tried in order; the first format that parses every value across every date
# column wins. ISO first (the canonical form), then the US slash form.
ACCEPTED_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",             # 2017-08-19  (canonical)
    "%m/%d/%Y",             # 8/19/2017   (US, month first)
)
# Same list in the form a user writes it, for error messages and the UI.
ACCEPTED_DATE_EXAMPLES = "2017-08-19 (ISO, preferred) or 8/19/2017"


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
        f"{ACCEPTED_DATE_EXAMPLES}"
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
