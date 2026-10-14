"""Settings read from the environment (.env in the project folder)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# Revision codes shown in the UI -> revision_number values stored in demand_forecast
REVISIONS: dict[str, str] = {"DA1": "DA-0900", "DA2": "DA-1700", "ID": "INTRADAY"}
REVISION_LABELS: dict[str, str] = {"DA1": "DA1 · DA-0900", "DA2": "DA2 · DA-1700", "ID": "ID · Intraday"}
ALL = "ALL"

# The four DISCOMs, in display order. "All DISCOMs · Total" = the sum of exactly these four.
# The southern DISCOM may be stored as TPSODL or TPSOSDL; whichever exists in the data is used.
# Any other discom_name in the tables (e.g. a stored total) is ignored.
DISCOM_ORDER = ["TPCODL", "TPWODL", "TPNODL", "TPSODL", "TPSOSDL"]

MAX_RANGE_MONTHS = 3  # custom period: up to three calendar months, both dates included


@dataclass(frozen=True)
class DbSettings:
    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "3306"))
    user: str = os.getenv("DB_USER", "root")
    password: str = os.getenv("DB_PASSWORD", "")
    name: str = os.getenv("DB_NAME", "odisha_demand_db")
    actual_table: str = os.getenv("ACTUAL_TABLE", "demand_blocks_discom")
    forecast_table: str = os.getenv("FORECAST_TABLE", "demand_forecast")


DB = DbSettings()