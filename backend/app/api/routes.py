from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import DB_PATH
from app.db import connect
from app.models.schemas import DashboardResponse, HealthResponse
from app.services.dashboard import build_dashboard, get_date_bounds

router = APIRouter(prefix="/api/v1")


def connection_dependency():
    connection = connect(DB_PATH)
    try:
        yield connection
    finally:
        connection.close()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    connection = connect(DB_PATH)
    try:
        row = connection.execute("SELECT 1 FROM sales_facts LIMIT 1").fetchone()
        if row is None:
            return HealthResponse(status="degraded", database_ready=False)
        return HealthResponse(status="ok", database_ready=True)
    except sqlite3.Error:
        return HealthResponse(status="degraded", database_ready=False)
    finally:
        connection.close()


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    connection: sqlite3.Connection = Depends(connection_dependency),
) -> DashboardResponse:
    if (start_date is None) != (end_date is None):
        raise HTTPException(status_code=422, detail="start_date 和 end_date 必须同时提供。")
    bounds = get_date_bounds(connection)
    if bounds is None:
        raise HTTPException(status_code=503, detail="数据库尚未导入销售数据。")
    if start_date is None and end_date is None:
        start_date, end_date = bounds
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date 不能晚于 end_date。")
    return DashboardResponse.model_validate(build_dashboard(connection, start_date, end_date))
