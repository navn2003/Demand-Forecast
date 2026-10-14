"""Demand Forecast Monitor — FastAPI app.

Run from the project folder:
    uvicorn app.main:app --reload
then open http://127.0.0.1:8000
"""

from __future__ import annotations

import csv
import io
import os
from datetime import date

import pymysql
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import ALL, REVISION_LABELS, REVISIONS
from .export import build_workbook
from .report import availability, build_report, list_discoms, validate_period

STATIC = os.path.join(os.path.dirname(__file__), "static")
app = FastAPI(title="Demand Forecast Monitor")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _db_error(e: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=f"Database error: {e}")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/meta")
def meta() -> dict:
    try:
        discoms = list_discoms()
        avail = availability()
    except pymysql.MySQLError as e:
        raise _db_error(e)
    return {
        "discoms": [{"value": ALL, "label": "All DISCOMs · Total", "members": discoms}]
                   + [{"value": d, "label": d} for d in discoms],
        "revisions": [{"value": ALL, "label": "All Revisions"}]
                     + [{"value": k, "label": REVISION_LABELS[k], "db_value": v} for k, v in REVISIONS.items()],
        "available": avail,
    }


def _report(discom: str, revision: str, start: date, end: date) -> dict:
    try:
        return build_report(discom, revision, start, end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except pymysql.MySQLError as e:
        raise _db_error(e)


@app.get("/api/report")
def report(
    discom: str = Query(ALL),
    revision: str = Query(ALL),
    start: date = Query(...),
    end: date = Query(...),
) -> dict:
    return _report(discom, revision, start, end)


@app.get("/api/report.csv")
def report_csv(
    discom: str = Query(ALL),
    revision: str = Query(ALL),
    start: date = Query(...),
    end: date = Query(...),
) -> StreamingResponse:
    rep = _report(discom, revision, start, end)
    buf = io.StringIO()
    w = csv.writer(buf)
    revs = rep["revisions"]
    w.writerow(["timestamp", "discom", "actual_mw"]
               + [f"{r}_forecast_mw" for r in revs] + [f"{r}_ape_pct" for r in revs])
    scope = "ALL_DISCOMS_TOTAL" if discom == ALL else discom
    for row in rep["series"]:
        a = row["actual"]
        apes = [round(abs(a - row[r]) / a * 100, 2) if a and row[r] is not None else "" for r in revs]
        w.writerow([row["ts"], scope, "" if a is None else a]
                   + ["" if row[r] is None else row[r] for r in revs] + apes)
    w.writerow([])
    w.writerow(["revision", "matched_blocks", "avg_actual_mw", "avg_forecast_mw", "mape_pct"])
    for s in rep["summary"]:
        w.writerow([s["label"], s["matched_blocks"], s["avg_actual"], s["avg_forecast"], s["mape"]])
    name = f"demand_{scope}_{revision}_{start}_{end}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/report.xlsx")
def report_xlsx(start: date = Query(...), end: date = Query(...)) -> StreamingResponse:
    """Workbook with one sheet per DISCOM plus ODISHA_SUM, all three revisions, for the period."""
    try:
        validate_period(start, end)
        data, name = build_workbook(start, end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except pymysql.MySQLError as e:
        raise _db_error(e)
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )