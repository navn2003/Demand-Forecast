"""Report logic: actual vs forecast per revision, and MAPE.

MAPE (per revision) = average over matched blocks of |Actual - Forecast| / Actual x 100.
A block is "matched" when both an actual (> 0) and a forecast exist for that timestamp.
Average actual and average forecast are taken over the same matched blocks, so the three
numbers in a row always describe the same set of intervals.

"All DISCOMs · Total" = TPCODL + TPWODL + TPNODL + TPSODL at each timestamp. Only these four are
summed (any other discom_name, such as a stored total, is ignored), and only timestamps where all
four have a value are kept (for actuals and for each revision separately). If a DISCOM/timestamp has
several rows, the most recent row (highest id) is used.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .config import ALL, DB, DISCOM_ORDER, MAX_RANGE_MONTHS, REVISION_LABELS, REVISIONS
from .db import fetch_all

A, F = DB.actual_table, DB.forecast_table


# ---------- metadata --------------------------------------------------------------------------

def list_discoms() -> list[str]:
    """The four DISCOMs present in the actuals table, in display order."""
    rows = fetch_all(f"SELECT DISTINCT discom_name FROM `{A}`")
    names = {r["discom_name"] for r in rows if r["discom_name"]}
    return [d for d in DISCOM_ORDER if d in names]


def availability() -> dict:
    a = fetch_all(f"SELECT MIN(block_start_ts) AS lo, MAX(block_start_ts) AS hi FROM `{A}`")[0]
    f = fetch_all(f"SELECT MIN(`timestamp`) AS lo, MAX(`timestamp`) AS hi FROM `{F}`")[0]
    iso = lambda v: v.date().isoformat() if v else None  # noqa: E731
    return {"actual_from": iso(a["lo"]), "actual_to": iso(a["hi"]),
            "forecast_from": iso(f["lo"]), "forecast_to": iso(f["hi"])}


# ---------- period validation -----------------------------------------------------------------

def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    last = (date(y + (m // 12), m % 12 + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(d.day, last))


def validate_period(start: date, end: date) -> None:
    if end < start:
        raise ValueError("The end date is before the start date.")
    if end > add_months(start, MAX_RANGE_MONTHS) - timedelta(days=1):
        raise ValueError("Choose up to three calendar months.")


# ---------- data ------------------------------------------------------------------------------

def _actuals(discom: str, lo: datetime, hi: datetime, members: list[str]) -> dict[datetime, float]:
    latest = (f"SELECT MAX(id) AS id FROM `{A}` WHERE block_start_ts >= %s AND block_start_ts < %s "
              "{extra} GROUP BY discom_name, block_start_ts")
    if discom == ALL:
        marks = ",".join(["%s"] * len(members))
        sql = (f"SELECT a.block_start_ts AS ts, SUM(a.demand_mw) AS v, COUNT(a.demand_mw) AS n "
               f"FROM `{A}` a JOIN ({latest.format(extra=f'AND discom_name IN ({marks})')}) x ON x.id = a.id "
               "GROUP BY a.block_start_ts HAVING n = %s")
        rows = fetch_all(sql, (lo, hi, *members, len(members)))
    else:
        sql = (f"SELECT a.block_start_ts AS ts, a.demand_mw AS v FROM `{A}` a "
               f"JOIN ({latest.format(extra='AND discom_name = %s')}) x ON x.id = a.id")
        rows = fetch_all(sql, (lo, hi, discom))
    return {r["ts"]: float(r["v"]) for r in rows if r["v"] is not None}


def _forecasts(discom: str, revs: list[str], lo: datetime, hi: datetime, members: list[str]) -> dict[str, dict[datetime, float]]:
    db_revs = [REVISIONS[r] for r in revs]
    marks = ",".join(["%s"] * len(db_revs))
    latest = (f"SELECT MAX(id) AS id FROM `{F}` WHERE `timestamp` >= %s AND `timestamp` < %s "
              f"AND revision_number IN ({marks}) {{extra}} GROUP BY discom_name, revision_number, `timestamp`")
    if discom == ALL:
        dmarks = ",".join(["%s"] * len(members))
        sql = (f"SELECT f.`timestamp` AS ts, f.revision_number AS rev, SUM(f.forecast_mw) AS v, COUNT(f.forecast_mw) AS n "
               f"FROM `{F}` f JOIN ({latest.format(extra=f'AND discom_name IN ({dmarks})')}) x ON x.id = f.id "
               "GROUP BY f.revision_number, f.`timestamp` HAVING n = %s")
        rows = fetch_all(sql, (lo, hi, *db_revs, *members, len(members)))
    else:
        sql = (f"SELECT f.`timestamp` AS ts, f.revision_number AS rev, f.forecast_mw AS v FROM `{F}` f "
               f"JOIN ({latest.format(extra='AND discom_name = %s')}) x ON x.id = f.id")
        rows = fetch_all(sql, (lo, hi, *db_revs, discom))
    back = {v: k for k, v in REVISIONS.items()}
    out: dict[str, dict[datetime, float]] = {r: {} for r in revs}
    for r in rows:
        if r["v"] is not None and r["rev"] in back:
            out[back[r["rev"]]][r["ts"]] = float(r["v"])
    return out


def build_report(discom: str, revision: str, start: date, end: date) -> dict:
    validate_period(start, end)
    discoms = list_discoms()
    if discom != ALL and discom not in discoms:
        raise ValueError(f"Unknown DISCOM: {discom}")
    revs = list(REVISIONS) if revision == ALL else [revision]
    if revision != ALL and revision not in REVISIONS:
        raise ValueError(f"Unknown revision: {revision}")

    lo = datetime.combine(start, datetime.min.time())
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time())
    actual = _actuals(discom, lo, hi, discoms)
    fc = _forecasts(discom, revs, lo, hi, discoms)

    # full 15-minute grid for the period, so gaps show as gaps
    grid, t = [], lo
    while t < hi:
        grid.append(t)
        t += timedelta(minutes=15)

    series = []
    for ts in grid:
        row = {"ts": ts.strftime("%Y-%m-%d %H:%M"), "actual": _r(actual.get(ts))}
        for r in revs:
            row[r] = _r(fc[r].get(ts))
        series.append(row)

    summary = []
    for r in revs:
        pairs = [(actual[ts], fc[r][ts]) for ts in grid if ts in fc[r] and actual.get(ts, 0) > 0]
        n = len(pairs)
        summary.append({
            "revision": r,
            "label": REVISION_LABELS[r],
            "db_revision": REVISIONS[r],
            "matched_blocks": n,
            "avg_actual": _r(sum(a for a, _ in pairs) / n) if n else None,
            "avg_forecast": _r(sum(f for _, f in pairs) / n) if n else None,
            "mape": round(sum(abs(a - f) / a for a, f in pairs) / n * 100, 2) if n else None,
        })

    return {
        "discom": discom,
        "total_of": discoms if discom == ALL else None,
        "revision": revision,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "blocks_in_period": len(grid),
        "actual_blocks": sum(1 for ts in grid if ts in actual),
        "revisions": revs,
        "summary": summary,
        "series": series,
    }


def _r(v: float | None) -> float | None:
    return None if v is None else round(v, 2)