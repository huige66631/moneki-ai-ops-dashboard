from __future__ import annotations

from datetime import date
from pydantic import BaseModel


class DateRange(BaseModel):
    start_date: date
    end_date: date


class Summary(BaseModel):
    revenue: float
    order_count: int
    average_order_value: float | None


class DailyPoint(BaseModel):
    date: date
    revenue: float
    order_count: int
    average_order_value: float | None


class TopProduct(BaseModel):
    rank: int
    product_id: str
    product_name: str
    product_category: str | None
    revenue: float
    order_count: int
    revenue_share: float


class DataQuality(BaseModel):
    included_record_count: int
    excluded_duplicate_count: int
    excluded_invalid_amount_count: int
    unmatched_store_count: int
    unmatched_product_count: int


class DashboardResponse(BaseModel):
    range: DateRange
    summary: Summary
    daily: list[DailyPoint]
    top_products: list[TopProduct]
    data_quality: DataQuality


class HealthResponse(BaseModel):
    status: str
    database_ready: bool
