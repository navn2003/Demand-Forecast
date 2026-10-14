# Demand Forecast Monitor

FastAPI dashboard comparing actual demand with day-ahead and intra-day forecasts for the Odisha DISCOMs.

## Data
- Actuals: `demand_blocks_discom` (`block_start_ts`, `discom_name`, `demand_mw`)
- Forecasts: `demand_forecast` (`timestamp`, `discom_name`, `revision_number`, `forecast_mw`)
- Revisions: DA1 = `DA-0900`, DA2 = `DA-1700`, ID = `INTRADAY`
- **All DISCOMs · Total** sums the DISCOMs at each 15-minute timestamp, using only timestamps where every DISCOM has a value.
- If one DISCOM/timestamp has several rows, the latest row (highest `id`) is used.

## MAPE
MAPE = average of |Actual − Forecast| ÷ Actual × 100 over matched 15-minute intervals (actual > 0 and forecast present).
Average actual and average forecast use the same matched intervals.

## Run (Windows, VS Code terminal)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000

Database settings are in `.env` (copy `.env.example` if it is missing).

## API
- `GET /api/meta` — DISCOM list, revisions, available date ranges
- `GET /api/report?discom=ALL|TPCODL|...&revision=ALL|DA1|DA2|ID&start=YYYY-MM-DD&end=YYYY-MM-DD`
- `GET /api/report.csv` — same parameters, CSV download
Periods are limited to three calendar months.
