"""Pydantic response schemas for the HQ Dashboard REST API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, computed_field

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class AlertOut(BaseModel):
    alert_id: str
    station_id: str
    severity: str
    domain: str
    asset_id: Optional[str] = None
    triggered_at: datetime
    description: str
    ack_state: str
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    black_box_activated: bool = False
    synced_to_cloud: bool = False

    @computed_field  # type: ignore[misc]
    @property
    def duration_open_s(self) -> float:
        end = self.resolved_at or datetime.utcnow().replace(tzinfo=self.triggered_at.tzinfo)
        return max(0.0, (end - self.triggered_at).total_seconds())

    model_config = {"from_attributes": True}


class AlertAcknowledgeIn(BaseModel):
    acknowledged_by: str


# ---------------------------------------------------------------------------
# Stations
# ---------------------------------------------------------------------------

class StationConnectionOut(BaseModel):
    station_id: str
    display_name: str
    link_state: str
    last_heartbeat_at: Optional[datetime] = None
    queue_depth_bytes: Optional[int] = None
    open_critical_alerts: Optional[int] = None
    open_high_alerts: Optional[int] = None
    services_healthy: Optional[bool] = None
    minutes_since_heartbeat: Optional[float] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------

class SensorSummaryOut(BaseModel):
    station_id: str
    sensor_id: str
    domain: str
    latest_value: Optional[float] = None
    latest_unit: Optional[str] = None
    latest_ts: Optional[datetime] = None
    readings_count_24h: int
    quality: Optional[str] = None  # NOMINAL | SUSPECT | FAILED


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

class AnalyticsOut(BaseModel):
    station_id: str
    period_hours: float
    alert_counts_by_severity: Dict[str, int]
    total_readings: int
    avg_readings_per_hour: float
    open_alerts_total: int


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardSummaryOut(BaseModel):
    stations: List[StationConnectionOut]
    total_open_critical: int
    total_open_high: int
    total_open_alerts: int
    generated_at: datetime


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    items: List[Any]


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class InventoryItemOut(BaseModel):
    item_id: str
    station_id: str
    category: str
    name: str
    quantity: float
    unit: str
    min_safety_threshold: Optional[float] = None
    daily_burn_rate: Optional[float] = None
    days_remaining: Optional[int] = None
    last_updated: Optional[datetime] = None
    status: str = "NOMINAL"          # computed in endpoint

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

class AssetOut(BaseModel):
    asset_id: str
    station_id: str
    asset_type: str
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation_m: Optional[float] = None
    status: str
    commissioned_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Resupply
# ---------------------------------------------------------------------------

class ResupplyLineItemOut(BaseModel):
    line_item_id: str
    item_name: str
    quantity_delivered: float
    unit: str

    model_config = {"from_attributes": True}


class ResupplyManifestOut(BaseModel):
    manifest_id: str
    station_id: str
    expedition_name: Optional[str] = None
    voyage_year: int
    ship_name: Optional[str] = None
    departure_date: Optional[datetime] = None
    arrival_window_start: Optional[datetime] = None
    arrival_window_end: Optional[datetime] = None
    status: str
    notes: Optional[str] = None
    line_items: List[ResupplyLineItemOut] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# AI Predictions
# ---------------------------------------------------------------------------

class AIPredictionOut(BaseModel):
    prediction_id: str
    station_id: str
    model_name: str
    target_metric: str
    predicted_value: Optional[float] = None
    confidence_lower: Optional[float] = None
    confidence_upper: Optional[float] = None
    risk_level: str
    predicted_for_date: Optional[datetime] = None
    generated_at: datetime

    model_config = {"from_attributes": True}
