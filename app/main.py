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

from urllib.parse import parse_qs, quote

import pymysql
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .auth import COOKIE_NAME, check_credentials, is_public, make_session, read_session, safe_next
from .config import ALL, AUTH, REVISION_LABELS, REVISIONS
from .export import build_workbook
from .report import availability, build_report, list_discoms, validate_period

STATIC = os.path.join(os.path.dirname(__file__), "static")
app = FastAPI(title="Demand Forecast Monitor")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Every page and API call needs a valid session, except the login page and static files."""
    path = request.url.path
    if is_public(path) or read_session(request.cookies.get(COOKIE_NAME)):
        response = await call_next(request)
        if path.startswith("/static/") or path in ("/", "/login"):
            # Browser must re-check with the server each time, so edited CSS/JS show up without a hard refresh
            response.headers["Cache-Control"] = "no-cache"
        return response
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Not logged in"}, status_code=401)
    return RedirectResponse(f"/login?next={quote(path)}", status_code=303)


def _db_error(e: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=f"Database error: {e}")


@app.get("/login")
def login_page(request: Request):
    if read_session(request.cookies.get(COOKIE_NAME)):
        return RedirectResponse(safe_next(request.query_params.get("next")), status_code=303)
    return FileResponse(os.path.join(STATIC, "login.html"))


@app.post("/login")
async def login_submit(request: Request) -> RedirectResponse:
    # Plain HTML form post (application/x-www-form-urlencoded), parsed by hand so no extra package is needed
    form = parse_qs((await request.body()).decode("utf-8"))
    username = form.get("username", [""])[0].strip()
    password = form.get("password", [""])[0]
    nxt = safe_next(form.get("next", ["/"])[0])
    if not check_credentials(username, password):
        return RedirectResponse(f"/login?error=1&next={quote(nxt)}", status_code=303)
    resp = RedirectResponse(nxt, status_code=303)
    resp.set_cookie(COOKIE_NAME, make_session(username), max_age=AUTH.session_hours * 3600,
                    httponly=True, samesite="lax", secure=request.url.scheme == "https")
    return resp


@app.post("/logout")
def logout() -> RedirectResponse:
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.get("/api/me")
def me(request: Request) -> dict:
    return {"username": read_session(request.cookies.get(COOKIE_NAME))}


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