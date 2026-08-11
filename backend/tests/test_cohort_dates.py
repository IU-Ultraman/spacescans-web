"""Cohort date-format resolution (app/cohort_dates.py).

Regression origin: a cohort with US-style dates passed upload (pandas'
parse_dates inference accepted it) and then failed mid-run with
`csv_to_parquet failed: ValueError('time data "8/19/2017" doesn't match
format "%Y-%m-%d"')`. Upload and the runner now share one resolver.
"""
import pandas as pd
import pytest

from app.cohort_dates import detect_date_format, parse_date_columns
from app.experiments.bg_ndi_wi import csv_to_parquet


def _df(start, end):
    return pd.DataFrame({"startDate": start, "endDate": end})


def test_us_slash_dates_parse_month_first():
    """The reported failure: 8/19/2017 is 19 August, not an error."""
    out = parse_date_columns(_df(["8/19/2017"], ["12/1/2016"]))
    assert out["startDate"].iloc[0] == pd.Timestamp("2017-08-19")
    assert out["endDate"].iloc[0] == pd.Timestamp("2016-12-01")


def test_iso_dates_still_parse():
    out = parse_date_columns(_df(["2017-08-19"], ["2017-09-20"]))
    assert out["startDate"].iloc[0] == pd.Timestamp("2017-08-19")


def test_ambiguous_dates_resolve_month_first():
    """3/4/2017 can't be settled by the data; these cohorts are US."""
    out = parse_date_columns(_df(["3/4/2017"], ["5/6/2017"]))
    assert out["startDate"].iloc[0] == pd.Timestamp("2017-03-04")
    assert out["endDate"].iloc[0] == pd.Timestamp("2017-05-06")


@pytest.mark.parametrize("value", [
    "8/19/17",       # two-digit year — which century?
    "8-19-2017",
    "2017/08/19",
    "19-Aug-2017",
    "Aug 19, 2017",
    "19/8/2017",     # day-first: no longer reinterpreted, just rejected
    "2017-08-19 00:00:00",
])
def test_only_two_formats_are_accepted(value):
    """Everything outside ISO and US month-first is refused at the door.

    Each of these is one re-export away from a supported form, while every
    extra candidate is another way for a file to parse as a date nobody
    meant — 8/19/17 has to guess a century, and 19/8/2017 used to be read as
    19 August purely because no month has 19.
    """
    with pytest.raises(ValueError, match="Unrecognized date format"):
        parse_date_columns(_df([value], [value]))


def test_error_names_both_accepted_forms():
    with pytest.raises(ValueError) as e:
        parse_date_columns(_df(["19-Aug-2017"], ["20-Aug-2017"]))
    msg = str(e.value)
    assert "2017-08-19" in msg and "8/19/2017" in msg
    assert "%" not in msg  # user-facing examples, not strftime codes


def test_one_format_is_shared_across_columns():
    """A column pair must agree — never start month-first, end day-first."""
    with pytest.raises(ValueError, match="Unrecognized date format"):
        parse_date_columns(_df(["8/19/2017"], ["2017-09-20"]))


def test_mixed_formats_within_a_column_are_rejected():
    """Whole-column match only; no per-element inference."""
    with pytest.raises(ValueError, match="Unrecognized date format"):
        parse_date_columns(_df(["8/19/2017", "2017-09-20"], ["9/1/2017", "9/2/2017"]))


def test_unparseable_dates_raise_with_the_offending_value():
    with pytest.raises(ValueError, match="not-a-date"):
        parse_date_columns(_df(["not-a-date"], ["also-bad"]))


def test_blank_cells_become_nat_not_errors():
    out = parse_date_columns(_df(["8/19/2017", ""], ["9/20/2017", "9/21/2017"]))
    assert out["startDate"].iloc[0] == pd.Timestamp("2017-08-19")
    assert pd.isna(out["startDate"].iloc[1])


def test_detect_prefers_iso():
    assert detect_date_format([pd.Series(["2017-08-19"])]) == "%Y-%m-%d"


def test_csv_to_parquet_accepts_us_slash_dates(tmp_path):
    """End-to-end: the exact CSV shape that used to crash the runner."""
    src = tmp_path / "input.csv"
    src.write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "PID0000001,8/19/2017,11/11/2017,-93.028635,45.088976\n"
        "PID0000002,3/24/2017,6/21/2017,-95.345115,29.738952\n"
    )
    dst = tmp_path / "input.parquet"
    csv_to_parquet(src, dst)

    df = pd.read_parquet(dst)
    assert pd.api.types.is_datetime64_any_dtype(df["startDate"])
    assert df["startDate"].iloc[0] == pd.Timestamp("2017-08-19")
    assert df["endDate"].iloc[1] == pd.Timestamp("2017-06-21")
