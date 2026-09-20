"""HQ Dashboard REST API — Phase 5.

All endpoints are under /api/v1/hq/ and provide a global view across
both Antarctic research stations for the NCPOR HQ operations team.

Endpoints:
  GET  /api/v1/hq/dashboard                       Global summary
  GET  /api/v1/hq/stations                        All station statuses
  GET  /api/v1/hq/stations/{station_id}/status    Single station status
  GET  /api/v1/hq/alerts                          Paginated alerts
  GET  /api/v1/hq/alerts/{alert_id}               Alert detail
  PATCH /api/v1/hq/alerts/{alert_id}/acknowledge  Acknowledge alert
  GET  /api/v1/hq/stations/{station_id}/sensors   Latest sensor readings (domain filter)
  GET  /api/v1/hq/stations/{station_id}/sensors/{sensor_id}  Sensor history
  GET  /api/v1/hq/stations/{station_id}/analytics 24h analytics
  GET  /api/v1/hq/stations/{station_id}/inventory Inventory items
  GET  /api/v1/hq/stations/{station_id}/assets    Infrastructure assets
  GET  /api/v1/hq/resupply                        Latest resupply manifest
  GET  /api/v1/hq/stations/{station_id}/predictions  AI predictions
  GET  /api/v1/hq/health                          Health check
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models.cloud import (
    AIPrediction,
    Asset,
    ResupplyLineItem,
    ResupplyManifest,
    StationConnection,
)
from shared.db.models.edge import Alert, InventoryItem, SensorReading
from shared.utils.time import utcnow
from cloud.api.schemas import (
    AIPredictionOut,
    AlertAcknowledgeIn,
    AlertOut,
    AnalyticsOut,
    AssetOut,
    DashboardSummaryOut,
    InventoryItemOut,
    PaginatedResponse,
    ResupplyManifestOut,
    ResupplyLineItemOut,
    SensorSummaryOut,
    StationConnectionOut,
)
from cloud.auth.deps import get_current_user, require_operator
from cloud.config import get_config
from cloud.deps import get_db_session

log = structlog.get_logger(__name__)

# All HQ endpoints require a valid JWT — applied at router level
router = APIRouter(
    prefix="/api/v1/hq",
    tags=["hq-dashboard"],
    dependencies=[Depends(get_current_user)],
)


_STATION_DISPLAY = {
    "maitri": "Maitri Research Station",
    "bharati": "Bharati Research Station",
}


def _station_display(station_id: str) -> str:
    return _STATION_DISPLAY.get(station_id, station_id.title())


def _compute_inventory_status(item: InventoryItem) -> str:
    """Derive NOMINAL / WARNING / CRITICAL from quantity vs threshold."""
    if item.min_safety_threshold and item.quantity <= item.min_safety_threshold * 0.5:
        return "CRITICAL"
    if item.min_safety_threshold and item.quantity <= item.min_safety_threshold:
        return "WARNING"
    return "NOMINAL"


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=DashboardSummaryOut)
async def get_dashboard(
    session: AsyncSession = Depends(get_db_session),
) -> DashboardSummaryOut:
    """Return global health summary across all stations."""
    cfg = get_config()
    station_outs = []
    total_critical = total_high = total_open = 0

    for sid in cfg.station_ids:
        conn_result = await session.execute(
            select(StationConnection).where(StationConnection.station_id == sid)
        )
        conn = conn_result.scalar_one_or_none()

        for sev, target in [("CRITICAL", "critical"), ("HIGH", "high")]:
            cnt_result = await session.execute(
                select(func.count(Alert.alert_id))
                .where(Alert.station_id == sid)
                .where(Alert.severity == sev)
                .where(Alert.ack_state != "RESOLVED")
            )
            n = cnt_result.scalar_one() or 0
            if sev == "CRITICAL":
                total_critical += n
            else:
                total_high += n

        total_result = await session.execute(
            select(func.count(Alert.alert_id))
            .where(Alert.station_id == sid)
            .where(Alert.ack_state != "RESOLVED")
        )
        total_open += total_result.scalar_one() or 0

        if conn:
            minutes_since = None
            if conn.last_heartbeat_at:
                delta = utcnow() - conn.last_heartbeat_at.replace(tzinfo=timezone.utc)
                minutes_since = delta.total_seconds() / 60
            station_outs.append(StationConnectionOut(
                station_id=sid,
                display_name=_station_display(sid),
                link_state=conn.link_state,
                last_heartbeat_at=conn.last_heartbeat_at,
                queue_depth_bytes=conn.queue_depth_bytes,
                open_critical_alerts=conn.open_critical_alerts,
                open_high_alerts=conn.open_high_alerts,
                services_healthy=conn.services_healthy,
                minutes_since_heartbeat=minutes_since,
            ))
        else:
            station_outs.append(StationConnectionOut(
                station_id=sid,
                display_name=_station_display(sid),
                link_state="DOWN",
                last_heartbeat_at=None,
                queue_depth_bytes=None,
                open_critical_alerts=None,
                open_high_alerts=None,
                services_healthy=None,
                minutes_since_heartbeat=None,
            ))

    return DashboardSummaryOut(
        stations=station_outs,
        total_open_critical=total_critical,
        total_open_high=total_high,
        total_open_alerts=total_open,
        generated_at=utcnow(),
    )


# ---------------------------------------------------------------------------
# Stations
# ---------------------------------------------------------------------------

@router.get("/stations", response_model=List[StationConnectionOut])
async def list_stations(
    session: AsyncSession = Depends(get_db_session),
) -> List[StationConnectionOut]:
    result = await session.execute(select(StationConnection))
    rows = result.scalars().all()
    out = []
    for r in rows:
        minutes_since = None
        if r.last_heartbeat_at:
            delta = utcnow() - r.last_heartbeat_at.replace(tzinfo=timezone.utc)
            minutes_since = delta.total_seconds() / 60
        out.append(StationConnectionOut(
            station_id=r.station_id,
            display_name=_station_display(r.station_id),
            link_state=r.link_state,
            last_heartbeat_at=r.last_heartbeat_at,
            queue_depth_bytes=r.queue_depth_bytes,
            open_critical_alerts=r.open_critical_alerts,
            open_high_alerts=r.open_high_alerts,
            services_healthy=r.services_healthy,
            minutes_since_heartbeat=minutes_since,
        ))
    return out


@router.get("/stations/{station_id}/status", response_model=StationConnectionOut)
async def get_station_status(
    station_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> StationConnectionOut:
    result = await session.execute(
        select(StationConnection).where(StationConnection.station_id == station_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"Station {station_id!r} not found")
    minutes_since = None
    if row.last_heartbeat_at:
        delta = utcnow() - row.last_heartbeat_at.replace(tzinfo=timezone.utc)
        minutes_since = delta.total_seconds() / 60
    return StationConnectionOut(
        station_id=row.station_id,
        display_name=_station_display(row.station_id),
        link_state=row.link_state,
        last_heartbeat_at=row.last_heartbeat_at,
        queue_depth_bytes=row.queue_depth_bytes,
        open_critical_alerts=row.open_critical_alerts,
        open_high_alerts=row.open_high_alerts,
        services_healthy=row.services_healthy,
        minutes_since_heartbeat=minutes_since,
    )


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@router.get("/alerts", response_model=PaginatedResponse)
async def list_alerts(
    station_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    ack_state: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse:
    q = select(Alert)
    if station_id:
        q = q.where(Alert.station_id == station_id)
    if severity:
        q = q.where(Alert.severity == severity.upper())
    if ack_state:
        q = q.where(Alert.ack_state == ack_state.upper())

    total = (await session.execute(
        select(func.count()).select_from(q.subquery())
    )).scalar_one() or 0

    q = q.order_by(Alert.triggered_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(q)).scalars().all()

    return PaginatedResponse(
        total=total, page=page, page_size=page_size,
        items=[AlertOut.model_validate(r) for r in rows],
    )


@router.get("/alerts/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> AlertOut:
    result = await session.execute(select(Alert).where(Alert.alert_id == alert_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"Alert {alert_id!r} not found")
    return AlertOut.model_validate(row)


@router.patch("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge_alert(
    alert_id: str,
    body: AlertAcknowledgeIn,
    session: AsyncSession = Depends(get_db_session),
    _op: dict = Depends(require_operator),
) -> AlertOut:
    result = await session.execute(select(Alert).where(Alert.alert_id == alert_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"Alert {alert_id!r} not found")
    if row.ack_state == "RESOLVED":
        raise HTTPException(409, "Alert already resolved")
    row.ack_state = "ACKNOWLEDGED"
    row.acknowledged_by = body.acknowledged_by
    row.acknowledged_at = utcnow()
    await session.commit()
    await session.refresh(row)
    log.info("cloud.api.alert_acknowledged", alert_id=alert_id, by=body.acknowledged_by)
    return AlertOut.model_validate(row)


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------

@router.get("/stations/{station_id}/sensors", response_model=List[SensorSummaryOut])
async def get_latest_sensors(
    station_id: str,
    domain: Optional[str] = Query(None, description="Filter by domain: weather, energy, seismic, glacial"),
    session: AsyncSession = Depends(get_db_session),
) -> List[SensorSummaryOut]:
    """Latest reading + 24h count per sensor for one station. Optionally filter by domain."""
    cutoff_24h = utcnow() - timedelta(hours=24)
    cutoff_recent = utcnow() - timedelta(days=7)   # 7d window — wide enough for static dev data

    # Latest value per sensor (last 2h)
    latest_q = (
        select(
            SensorReading.sensor_id,
            func.max(SensorReading.timestamp_utc).label("max_ts"),
        )
        .where(SensorReading.station_id == station_id)
        .where(SensorReading.timestamp_utc >= cutoff_recent)
    )
    if domain:
        latest_q = latest_q.where(SensorReading.domain == domain.lower())
    latest_subq = latest_q.group_by(SensorReading.sensor_id).subquery()

    latest_result = await session.execute(
        select(SensorReading)
        .join(
            latest_subq,
            (SensorReading.sensor_id == latest_subq.c.sensor_id)
            & (SensorReading.timestamp_utc == latest_subq.c.max_ts),
        )
    )
    latest_rows = {r.sensor_id: r for r in latest_result.scalars().all()}

    # 24h count per sensor
    count_q = (
        select(SensorReading.sensor_id, func.count(SensorReading.id).label("cnt"))
        .where(SensorReading.station_id == station_id)
        .where(SensorReading.timestamp_utc >= cutoff_24h)
    )
    if domain:
        count_q = count_q.where(SensorReading.domain == domain.lower())
    count_result = await session.execute(count_q.group_by(SensorReading.sensor_id))
    counts = {row[0]: row[1] for row in count_result.all()}

    out = []
    for sensor_id, r in latest_rows.items():
        out.append(SensorSummaryOut(
            station_id=station_id,
            sensor_id=sensor_id,
            domain=r.domain,
            latest_value=r.value,
            latest_unit=r.unit,
            latest_ts=r.timestamp_utc,
            readings_count_24h=counts.get(sensor_id, 0),
        ))
    return sorted(out, key=lambda x: x.sensor_id)


@router.get("/stations/{station_id}/sensors/{sensor_id:path}", response_model=List[dict])
async def get_sensor_history(
    station_id: str,
    sensor_id: str,
    hours: float = Query(24.0, ge=0.1, le=720.0),
    session: AsyncSession = Depends(get_db_session),
) -> List[dict]:
    cutoff = utcnow() - timedelta(hours=hours)
    result = await session.execute(
        select(SensorReading)
        .where(SensorReading.station_id == station_id)
        .where(SensorReading.sensor_id == sensor_id)
        .where(SensorReading.timestamp_utc >= cutoff)
        .order_by(SensorReading.timestamp_utc)
        .limit(10000)
    )
    rows = result.scalars().all()
    if not rows:
        raise HTTPException(404, f"No data for sensor {sensor_id!r}")
    return [
        {
            "timestamp_utc": r.timestamp_utc.isoformat(),
            "value": r.value,
            "unit": r.unit,
            "quality": r.quality,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@router.get("/stations/{station_id}/analytics", response_model=AnalyticsOut)
async def get_analytics(
    station_id: str,
    hours: float = Query(24.0, ge=1.0, le=720.0),
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsOut:
    cutoff = utcnow() - timedelta(hours=hours)
    alert_counts: dict = {}
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        cnt = (await session.execute(
            select(func.count(Alert.alert_id))
            .where(Alert.station_id == station_id)
            .where(Alert.severity == sev)
            .where(Alert.triggered_at >= cutoff)
        )).scalar_one() or 0
        alert_counts[sev] = cnt

    open_total = (await session.execute(
        select(func.count(Alert.alert_id))
        .where(Alert.station_id == station_id)
        .where(Alert.ack_state != "RESOLVED")
    )).scalar_one() or 0

    total_readings = (await session.execute(
        select(func.count(SensorReading.id))
        .where(SensorReading.station_id == station_id)
        .where(SensorReading.timestamp_utc >= cutoff)
    )).scalar_one() or 0

    return AnalyticsOut(
        station_id=station_id,
        period_hours=hours,
        alert_counts_by_severity=alert_counts,
        total_readings=total_readings,
        avg_readings_per_hour=total_readings / max(hours, 1),
        open_alerts_total=open_total,
    )


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@router.get("/stations/{station_id}/inventory", response_model=List[InventoryItemOut])
async def get_inventory(
    station_id: str,
    category: Optional[str] = Query(None, description="Filter: FUEL, FOOD, MEDICAL, SPARE_PARTS"),
    session: AsyncSession = Depends(get_db_session),
) -> List[InventoryItemOut]:
    """Return all inventory items for a station with computed status."""
    q = select(InventoryItem).where(InventoryItem.station_id == station_id)
    if category:
        q = q.where(InventoryItem.category == category.upper())
    q = q.order_by(InventoryItem.category, InventoryItem.name)
    rows = (await session.execute(q)).scalars().all()
    return [
        InventoryItemOut(
            item_id=r.item_id,
            station_id=r.station_id,
            category=r.category,
            name=r.name,
            quantity=r.quantity,
            unit=r.unit,
            min_safety_threshold=r.min_safety_threshold,
            daily_burn_rate=r.daily_burn_rate,
            days_remaining=r.days_remaining,
            last_updated=r.last_updated,
            status=_compute_inventory_status(r),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Logistics Audit Summary  (hardcoded until DB schema is extended)
# ---------------------------------------------------------------------------

_LOGISTICS_AUDIT: dict = {
    "maitri": {
        "food": {
            "total_items": 3,
            "items": [
                {"item_id": "maitri.food.dry_rations",    "name": "Dry Rations (2026 Stock)",   "current_stock": 4800,   "unit": "kg",         "reorder_qty": 1200,  "min_safe": 500,   "daily_use": "19.2 kg/day",   "days_left": 250, "status": "SAFE"},
                {"item_id": "maitri.food.frozen",         "name": "Frozen Food Stock",           "current_stock": 2100,   "unit": "kg",         "reorder_qty": 900,   "min_safe": 300,   "daily_use": "8.4 kg/day",    "days_left": 250, "status": "SAFE"},
                {"item_id": "maitri.food.emergency_pack", "name": "Emergency Food Packs",        "current_stock": 150,    "unit": "packs",      "reorder_qty": 50,    "min_safe": 30,    "daily_use": "0 packs/day",   "days_left": 365, "status": "SAFE"},
            ],
            "audit": {"last_verified_by": "Maitri Station Commander", "last_verified_at": "2026-09-15T08:00:00Z", "verified": True, "pending_maitri": False, "pending_bharati": True},
        },
        "fuel": {
            "total_items": 2,
            "items": [
                {"item_id": "maitri.fuel.aviation",       "name": "Aviation Turbine Fuel (ATF)", "current_stock": 12400,  "unit": "litres",     "reorder_qty": 8000,  "min_safe": 3000,  "daily_use": "48 litres/day", "days_left": 258, "status": "SAFE"},
                {"item_id": "maitri.fuel.diesel_main",    "name": "Diesel Fuel (Main Reserve)",  "current_stock": 136800, "unit": "litres",     "reorder_qty": 60000, "min_safe": 40000, "daily_use": "530 litres/day","days_left": 258, "status": "SAFE"},
            ],
            "audit": {"last_verified_by": "Maitri Station Commander", "last_verified_at": "2026-09-15T08:00:00Z", "verified": True, "pending_maitri": False, "pending_bharati": True},
        },
        "medical": {
            "total_items": 2,
            "items": [
                {"item_id": "maitri.med.emergency_kit",   "name": "Emergency Medical Kit",       "current_stock": 8,      "unit": "kits",       "reorder_qty": 2,     "min_safe": 2,     "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
                {"item_id": "maitri.med.oxygen_tanks",    "name": "Oxygen Cylinders",            "current_stock": 24,     "unit": "cylinders",  "reorder_qty": 12,    "min_safe": 6,     "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
            ],
            "audit": {"last_verified_by": "Station Medical Officer", "last_verified_at": "2026-09-10T10:00:00Z", "verified": True, "pending_maitri": False, "pending_bharati": True},
        },
        "spares": {
            "total_items": 5,
            "items": [
                {"item_id": "maitri.spare.generator_parts",  "name": "Generator Spare Parts",       "current_stock": 1,      "unit": "set",        "reorder_qty": 1,     "min_safe": 1,     "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
                {"item_id": "maitri.spare.snowcat_tracks",   "name": "Snow Cat Tracks",             "current_stock": 4,      "unit": "units",      "reorder_qty": 2,     "min_safe": 2,     "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
                {"item_id": "maitri.spare.hydraulic_fluid",  "name": "Hydraulic Fluid",             "current_stock": 200,    "unit": "litres",     "reorder_qty": 100,   "min_safe": 50,    "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
                {"item_id": "maitri.spare.heating_cables",   "name": "Heating Cables (50m)",        "current_stock": 10,     "unit": "rolls",      "reorder_qty": 5,     "min_safe": 3,     "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
                {"item_id": "maitri.spare.comm_modules",     "name": "VSAT Communication Modules",  "current_stock": 3,      "unit": "units",      "reorder_qty": 2,     "min_safe": 1,     "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
            ],
            "audit": {"last_verified_by": "Maitri Technical Officer", "last_verified_at": "2026-09-12T09:00:00Z", "verified": True, "pending_maitri": False, "pending_bharati": True},
        },
    },
    "bharati": {
        "food": {
            "total_items": 3,
            "items": [
                {"item_id": "bharati.food.dry_rations",   "name": "Dry Rations (2026 Stock)",   "current_stock": 5200,   "unit": "kg",         "reorder_qty": 1000,  "min_safe": 500,   "daily_use": "21 kg/day",     "days_left": 247, "status": "SAFE"},
                {"item_id": "bharati.food.frozen",        "name": "Frozen Food Stock",           "current_stock": 1800,   "unit": "kg",         "reorder_qty": 1000,  "min_safe": 300,   "daily_use": "7.2 kg/day",    "days_left": 250, "status": "SAFE"},
                {"item_id": "bharati.food.emergency_pack","name": "Emergency Food Packs",        "current_stock": 120,    "unit": "packs",      "reorder_qty": 60,    "min_safe": 30,    "daily_use": "0 packs/day",   "days_left": 365, "status": "SAFE"},
            ],
            "audit": {"last_verified_by": "Bharati Station Commander", "last_verified_at": "2026-09-14T08:00:00Z", "verified": True, "pending_maitri": True, "pending_bharati": False},
        },
        "fuel": {
            "total_items": 2,
            "items": [
                {"item_id": "bharati.fuel.aviation",      "name": "Aviation Turbine Fuel (ATF)", "current_stock": 9800,   "unit": "litres",     "reorder_qty": 10000, "min_safe": 3000,  "daily_use": "38 litres/day", "days_left": 257, "status": "SAFE"},
                {"item_id": "bharati.fuel.diesel_main",   "name": "Diesel Fuel (Main Reserve)",  "current_stock": 98000,  "unit": "litres",     "reorder_qty": 80000, "min_safe": 35000, "daily_use": "380 litres/day","days_left": 257, "status": "SAFE"},
            ],
            "audit": {"last_verified_by": "Bharati Station Commander", "last_verified_at": "2026-09-14T08:00:00Z", "verified": True, "pending_maitri": True, "pending_bharati": False},
        },
        "medical": {
            "total_items": 2,
            "items": [
                {"item_id": "bharati.med.emergency_kit",  "name": "Emergency Medical Kit",       "current_stock": 6,      "unit": "kits",       "reorder_qty": 2,     "min_safe": 2,     "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
                {"item_id": "bharati.med.oxygen_tanks",   "name": "Oxygen Cylinders",            "current_stock": 18,     "unit": "cylinders",  "reorder_qty": 10,    "min_safe": 6,     "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
            ],
            "audit": {"last_verified_by": "Station Medical Officer", "last_verified_at": "2026-09-09T10:00:00Z", "verified": True, "pending_maitri": True, "pending_bharati": False},
        },
        "spares": {
            "total_items": 5,
            "items": [
                {"item_id": "bharati.spare.generator_parts",  "name": "Generator Spare Parts",      "current_stock": 1,      "unit": "set",        "reorder_qty": 1,     "min_safe": 1,     "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
                {"item_id": "bharati.spare.snowcat_tracks",   "name": "Snow Cat Tracks",            "current_stock": 2,      "unit": "units",      "reorder_qty": 4,     "min_safe": 2,     "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
                {"item_id": "bharati.spare.hydraulic_fluid",  "name": "Hydraulic Fluid",            "current_stock": 150,    "unit": "litres",     "reorder_qty": 150,   "min_safe": 50,    "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
                {"item_id": "bharati.spare.heating_cables",   "name": "Heating Cables (50m)",       "current_stock": 7,      "unit": "rolls",      "reorder_qty": 5,     "min_safe": 3,     "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
                {"item_id": "bharati.spare.comm_modules",     "name": "VSAT Communication Modules", "current_stock": 2,      "unit": "units",      "reorder_qty": 3,     "min_safe": 1,     "daily_use": "N/A",           "days_left": 365, "status": "SAFE"},
            ],
            "audit": {"last_verified_by": "Bharati Technical Officer", "last_verified_at": "2026-09-11T09:00:00Z", "verified": True, "pending_maitri": True, "pending_bharati": False},
        },
    },
}


@router.get("/logistics/audit-summary")
async def get_logistics_audit_summary(
    station_id: Optional[str] = Query(None, description="Filter: maitri or bharati"),
) -> dict:
    """Return hardcoded logistics audit & tracking summary per category.

    Intended for the Maitri/Bharati dashboards to verify stock counts.
    Returns per-category totals, item-level detail, reorder quantities,
    and audit metadata (who verified and when).
    """
    if station_id and station_id.lower() in _LOGISTICS_AUDIT:
        return {
            "station_id": station_id.lower(),
            "categories": _LOGISTICS_AUDIT[station_id.lower()],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_source": "hardcoded_v1",
        }
    return {
        "stations": {sid: {"categories": cats} for sid, cats in _LOGISTICS_AUDIT.items()},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "hardcoded_v1",
    }


# ---------------------------------------------------------------------------
# IoT Sensor Registry  (hardcoded until DB schema is extended)
# ---------------------------------------------------------------------------

_IOT_SENSORS: dict = {
    "maitri": [
        # ── Temperature & Climate ──────────────────────────────────────────
        {
            "sensor_id": "MAI-TMP-001", "name": "Outdoor Ambient Temperature", "category": "temperature",
            "icon": "thermostat", "state": "online", "location": "Met Tower — NW Face",
            "parameters": [
                {"key": "temperature",      "label": "Ambient Temp",     "value": -18.2,  "unit": "°C",    "normal_range": "-70 to 5 °C"},
                {"key": "rate_of_change",   "label": "Temp Rate Change", "value": -0.4,   "unit": "°C/hr", "normal_range": "-2 to 2 °C/hr"},
                {"key": "sampling_interval","label": "Sampling Interval","value": 60,     "unit": "sec",   "normal_range": "60 sec"},
                {"key": "sensor_voltage",   "label": "Sensor Voltage",   "value": 3.27,   "unit": "V",     "normal_range": "3.0–3.6 V"},
            ],
        },
        {
            "sensor_id": "MAI-TMP-002", "name": "Living Quarters Indoor Temp", "category": "temperature",
            "icon": "thermostat", "state": "online", "location": "Module A — Corridor",
            "parameters": [
                {"key": "temperature",      "label": "Indoor Temp",      "value": 18.4,   "unit": "°C",    "normal_range": "16–22 °C"},
                {"key": "humidity",         "label": "Relative Humidity","value": 42.1,   "unit": "%",     "normal_range": "35–55 %"},
                {"key": "setpoint_delta",   "label": "Setpoint Delta",   "value": -0.6,   "unit": "°C",    "normal_range": "±2 °C"},
                {"key": "sensor_voltage",   "label": "Sensor Voltage",   "value": 3.30,   "unit": "V",     "normal_range": "3.0–3.6 V"},
            ],
        },
        {
            "sensor_id": "MAI-TMP-003", "name": "Generator Hall Temp Monitor", "category": "temperature",
            "icon": "thermostat", "state": "online", "location": "Generator Block — Engine Room",
            "parameters": [
                {"key": "temperature",      "label": "Engine Room Temp", "value": 32.6,   "unit": "°C",    "normal_range": "25–45 °C"},
                {"key": "exhaust_temp",     "label": "Exhaust Temp",     "value": 420.0,  "unit": "°C",    "normal_range": "350–500 °C"},
                {"key": "coolant_temp",     "label": "Coolant Temp",     "value": 88.2,   "unit": "°C",    "normal_range": "70–95 °C"},
                {"key": "sensor_voltage",   "label": "Sensor Voltage",   "value": 3.29,   "unit": "V",     "normal_range": "3.0–3.6 V"},
            ],
        },
        # ── Atmospheric Pressure ───────────────────────────────────────────
        {
            "sensor_id": "MAI-PRS-001", "name": "Barometric Pressure Sensor", "category": "pressure",
            "icon": "compress", "state": "online", "location": "Met Tower — Top Platform",
            "parameters": [
                {"key": "pressure",         "label": "Barometric Press", "value": 994.2,  "unit": "hPa",   "normal_range": "940–1030 hPa"},
                {"key": "pressure_trend",   "label": "3h Trend",         "value": -2.8,   "unit": "hPa/3h","normal_range": "-10 to 10 hPa/3h"},
                {"key": "altitude_corrected","label": "Altitude Corr.",  "value": 1042.1, "unit": "hPa",   "normal_range": "960–1050 hPa"},
                {"key": "sensor_health",    "label": "Sensor Health",    "value": 99.1,   "unit": "%",     "normal_range": ">95 %"},
            ],
        },
        {
            "sensor_id": "MAI-PRS-002", "name": "Fuel Tank Pressure Monitor", "category": "pressure",
            "icon": "compress", "state": "online", "location": "Fuel Farm — Tank F1",
            "parameters": [
                {"key": "tank_pressure",    "label": "Tank Headspace P.","value": 1.04,   "unit": "bar",   "normal_range": "0.9–1.1 bar"},
                {"key": "vapor_pressure",   "label": "Vapour Pressure",  "value": 0.18,   "unit": "bar",   "normal_range": "<0.25 bar"},
                {"key": "temperature",      "label": "Fuel Temp",        "value": -12.4,  "unit": "°C",    "normal_range": "-30 to 5 °C"},
                {"key": "ullage",           "label": "Ullage (headspace)","value": 18.2,  "unit": "%",     "normal_range": "10–30 %"},
            ],
        },
        # ── Fuel Level ─────────────────────────────────────────────────────
        {
            "sensor_id": "MAI-FUL-001", "name": "Diesel Reserve Level Sensor", "category": "fuel",
            "icon": "local_gas_station", "state": "online", "location": "Fuel Farm — Main Depot",
            "parameters": [
                {"key": "fuel_level",       "label": "Fuel Level",       "value": 81.4,   "unit": "%",     "normal_range": ">30 %"},
                {"key": "volume",           "label": "Volume Remaining",  "value": 136800, "unit": "L",     "normal_range": ">40 000 L"},
                {"key": "consumption_rate", "label": "Consumption Rate",  "value": 530,    "unit": "L/day", "normal_range": "<800 L/day"},
                {"key": "days_remaining",   "label": "Days Remaining",    "value": 258,    "unit": "days",  "normal_range": ">90 days"},
            ],
        },
        {
            "sensor_id": "MAI-FUL-002", "name": "Aviation Fuel (ATF) Monitor", "category": "fuel",
            "icon": "local_gas_station", "state": "online", "location": "Heliad — ATF Bladder",
            "parameters": [
                {"key": "fuel_level",       "label": "ATF Level",        "value": 62.0,   "unit": "%",     "normal_range": ">25 %"},
                {"key": "volume",           "label": "Volume Remaining",  "value": 12400,  "unit": "L",     "normal_range": ">3 000 L"},
                {"key": "contamination",    "label": "Water Content",     "value": 0.002,  "unit": "%vol",  "normal_range": "<0.01 %vol"},
                {"key": "temperature",      "label": "Fuel Temp",        "value": -15.2,  "unit": "°C",    "normal_range": "-40 to 5 °C"},
            ],
        },
        # ── Seismic ────────────────────────────────────────────────────────
        {
            "sensor_id": "MAI-SES-001", "name": "Seismic Activity Sensor", "category": "seismic",
            "icon": "earthquake", "state": "online", "location": "Foundation Slab — Central",
            "parameters": [
                {"key": "ground_velocity",  "label": "Peak Ground Vel.", "value": 0.003,  "unit": "mm/s",  "normal_range": "<2 mm/s"},
                {"key": "frequency",        "label": "Dominant Freq.",   "value": 4.2,    "unit": "Hz",    "normal_range": "1–20 Hz"},
                {"key": "richter_est",      "label": "Est. Magnitude",   "value": 0.1,    "unit": "Ml",    "normal_range": "<2.0 Ml"},
                {"key": "event_count_24h",  "label": "Events (24 h)",    "value": 0,      "unit": "events","normal_range": "<5"},
            ],
        },
        # ── Wildlife / Ecology ─────────────────────────────────────────────
        {
            "sensor_id": "MAI-WLD-001", "name": "Wildlife Proximity Sensor", "category": "wildlife",
            "icon": "pets", "state": "online", "location": "Station Perimeter — South Fence",
            "parameters": [
                {"key": "detection_count",  "label": "Detections (24 h)","value": 3,      "unit": "events","normal_range": "0–20"},
                {"key": "closest_approach", "label": "Min Distance",     "value": 42.0,   "unit": "m",     "normal_range": ">10 m"},
                {"key": "noise_level",      "label": "Ambient Noise",    "value": 38.4,   "unit": "dB",    "normal_range": "<70 dB"},
                {"key": "infrared_flux",    "label": "IR Flux (heat sig)","value": 0.12,  "unit": "W/m²",  "normal_range": ">0.05 W/m²"},
            ],
        },
        # ── Radiation ──────────────────────────────────────────────────────
        {
            "sensor_id": "MAI-RAD-001", "name": "UV / Solar Radiation Sensor", "category": "radiation",
            "icon": "wb_sunny", "state": "online", "location": "Roof Deck — South Aspect",
            "parameters": [
                {"key": "uv_index",         "label": "UV Index",         "value": 1.4,    "unit": "UVI",   "normal_range": "0–12 UVI"},
                {"key": "solar_irradiance", "label": "Solar Irradiance", "value": 312.0,  "unit": "W/m²",  "normal_range": "0–1400 W/m²"},
                {"key": "ozone_column",     "label": "Ozone Column",     "value": 298.0,  "unit": "DU",    "normal_range": "200–400 DU"},
                {"key": "uva_dose",         "label": "Daily UVA Dose",   "value": 0.42,   "unit": "kJ/m²", "normal_range": "<5 kJ/m²"},
            ],
        },
        # ── Meteorological ─────────────────────────────────────────────────
        {
            "sensor_id": "MAI-MET-001", "name": "Wind Speed & Direction", "category": "meteorological",
            "icon": "air", "state": "online", "location": "Met Tower — 10 m AGL",
            "parameters": [
                {"key": "wind_speed",       "label": "Wind Speed",       "value": 22.4,   "unit": "km/h",  "normal_range": "0–250 km/h"},
                {"key": "wind_direction",   "label": "Wind Direction",   "value": 248,    "unit": "°",     "normal_range": "0–360 °"},
                {"key": "gust_speed",       "label": "Peak Gust",        "value": 34.0,   "unit": "km/h",  "normal_range": "0–300 km/h"},
                {"key": "turbulence",       "label": "Turbulence Intens.","value": 0.12,  "unit": "TI",    "normal_range": "0–1"},
            ],
        },
        {
            "sensor_id": "MAI-MET-002", "name": "Snowfall & Precipitation Gauge", "category": "meteorological",
            "icon": "ac_unit", "state": "offline", "location": "Open Field — Station NE",
            "parameters": [
                {"key": "snowfall_rate",    "label": "Snowfall Rate",    "value": 0.0,    "unit": "mm/hr", "normal_range": "0–100 mm/hr"},
                {"key": "snow_depth",       "label": "Snow Depth",       "value": 142.0,  "unit": "cm",    "normal_range": "0–500 cm"},
                {"key": "visibility",       "label": "Visibility",       "value": 2.4,    "unit": "km",    "normal_range": "0–50 km"},
                {"key": "blizzard_risk",    "label": "Blizzard Risk",    "value": "MEDIUM","unit": "",      "normal_range": "LOW"},
            ],
        },
        # ── Structural / Strain ────────────────────────────────────────────
        {
            "sensor_id": "MAI-STR-001", "name": "Main Beam Strain Gauge", "category": "structural",
            "icon": "foundation", "state": "online", "location": "Main Building — Span Centre",
            "parameters": [
                {"key": "strain",           "label": "Strain",           "value": 182,    "unit": "μϵ",    "normal_range": "<250 μϵ"},
                {"key": "settlement",       "label": "Foundation Settle.","value": 12.0,  "unit": "mm",    "normal_range": "<25 mm"},
                {"key": "snow_load",        "label": "Roof Snow Load",   "value": 3.2,    "unit": "kN/m²", "normal_range": "<6 kN/m²"},
                {"key": "temperature",      "label": "Beam Temp",        "value": -8.1,   "unit": "°C",    "normal_range": "-60 to 60 °C"},
            ],
        },
        # ── Air Quality ────────────────────────────────────────────────────
        {
            "sensor_id": "MAI-AQI-001", "name": "Indoor Air Quality Monitor", "category": "air_quality",
            "icon": "air", "state": "online", "location": "Laboratory Block — Main Lab",
            "parameters": [
                {"key": "co2",              "label": "CO₂",              "value": 812,    "unit": "ppm",   "normal_range": "<1000 ppm"},
                {"key": "co",              "label": "CO",               "value": 2.0,    "unit": "ppm",   "normal_range": "<9 ppm"},
                {"key": "pm25",            "label": "PM2.5",            "value": 8.0,    "unit": "μg/m³", "normal_range": "<25 μg/m³"},
                {"key": "oxygen",          "label": "O₂ Concentration", "value": 20.9,   "unit": "%",     "normal_range": "19.5–23.5 %"},
            ],
        },
        # ── Fire & Safety ──────────────────────────────────────────────────
        {
            "sensor_id": "MAI-FIR-001", "name": "Smoke & Fire Detection Array", "category": "fire_safety",
            "icon": "local_fire_department", "state": "online", "location": "All Zones — Network",
            "parameters": [
                {"key": "smoke_density",    "label": "Smoke Density",    "value": 0.02,   "unit": "obs/m", "normal_range": "<0.1 obs/m"},
                {"key": "temp_rise_rate",   "label": "Temp Rise Rate",   "value": 0.1,    "unit": "°C/min","normal_range": "<8 °C/min"},
                {"key": "detectors_active", "label": "Detectors Online", "value": 24,     "unit": "/24",   "normal_range": "24/24"},
                {"key": "last_test",        "label": "Last System Test", "value": 14,     "unit": "days ago","normal_range": "<30 days"},
            ],
        },
        # ── Communications ─────────────────────────────────────────────────
        {
            "sensor_id": "MAI-COM-001", "name": "VSAT Link Quality Monitor", "category": "communications",
            "icon": "satellite_alt", "state": "online", "location": "Antenna Farm — VSAT Dish 1",
            "parameters": [
                {"key": "signal_strength",  "label": "Signal Strength",  "value": 8.4,    "unit": "dB",    "normal_range": ">5 dB"},
                {"key": "latency",          "label": "Round-trip Latency","value": 640,    "unit": "ms",    "normal_range": "<1500 ms"},
                {"key": "bandwidth",        "label": "Bandwidth",         "value": 2.1,    "unit": "Mbps",  "normal_range": ">0.5 Mbps"},
                {"key": "packet_loss",      "label": "Packet Loss",       "value": 0.2,    "unit": "%",     "normal_range": "<2 %"},
            ],
        },
    ],
    "bharati": [
        # ── Temperature ────────────────────────────────────────────────────
        {
            "sensor_id": "BHA-TMP-001", "name": "Outdoor Ambient Temperature", "category": "temperature",
            "icon": "thermostat", "state": "online", "location": "Met Mast — NE Face",
            "parameters": [
                {"key": "temperature",      "label": "Ambient Temp",     "value": -24.6,  "unit": "°C",    "normal_range": "-70 to 5 °C"},
                {"key": "rate_of_change",   "label": "Temp Rate Change", "value": -0.8,   "unit": "°C/hr", "normal_range": "-2 to 2 °C/hr"},
                {"key": "sampling_interval","label": "Sampling Interval","value": 60,     "unit": "sec",   "normal_range": "60 sec"},
                {"key": "sensor_voltage",   "label": "Sensor Voltage",   "value": 3.24,   "unit": "V",     "normal_range": "3.0–3.6 V"},
            ],
        },
        {
            "sensor_id": "BHA-TMP-002", "name": "Accommodation Module Temp", "category": "temperature",
            "icon": "thermostat", "state": "online", "location": "Berthing Module — B2",
            "parameters": [
                {"key": "temperature",      "label": "Indoor Temp",      "value": 19.6,   "unit": "°C",    "normal_range": "16–22 °C"},
                {"key": "humidity",         "label": "Relative Humidity","value": 39.4,   "unit": "%",     "normal_range": "35–55 %"},
                {"key": "setpoint_delta",   "label": "Setpoint Delta",   "value": 0.4,    "unit": "°C",    "normal_range": "±2 °C"},
                {"key": "sensor_voltage",   "label": "Sensor Voltage",   "value": 3.31,   "unit": "V",     "normal_range": "3.0–3.6 V"},
            ],
        },
        # ── Pressure ───────────────────────────────────────────────────────
        {
            "sensor_id": "BHA-PRS-001", "name": "Barometric Pressure Sensor", "category": "pressure",
            "icon": "compress", "state": "online", "location": "Met Mast — Top Platform",
            "parameters": [
                {"key": "pressure",         "label": "Barometric Press", "value": 988.6,  "unit": "hPa",   "normal_range": "940–1030 hPa"},
                {"key": "pressure_trend",   "label": "3h Trend",         "value": -5.1,   "unit": "hPa/3h","normal_range": "-10 to 10 hPa/3h"},
                {"key": "altitude_corrected","label": "Altitude Corr.",  "value": 1038.4, "unit": "hPa",   "normal_range": "960–1050 hPa"},
                {"key": "sensor_health",    "label": "Sensor Health",    "value": 98.6,   "unit": "%",     "normal_range": ">95 %"},
            ],
        },
        # ── Fuel ───────────────────────────────────────────────────────────
        {
            "sensor_id": "BHA-FUL-001", "name": "Diesel Reserve Level Sensor", "category": "fuel",
            "icon": "local_gas_station", "state": "online", "location": "Fuel Bund — Main Tank",
            "parameters": [
                {"key": "fuel_level",       "label": "Fuel Level",       "value": 74.2,   "unit": "%",     "normal_range": ">30 %"},
                {"key": "volume",           "label": "Volume Remaining",  "value": 98000,  "unit": "L",     "normal_range": ">35 000 L"},
                {"key": "consumption_rate", "label": "Consumption Rate",  "value": 380,    "unit": "L/day", "normal_range": "<600 L/day"},
                {"key": "days_remaining",   "label": "Days Remaining",    "value": 257,    "unit": "days",  "normal_range": ">90 days"},
            ],
        },
        # ── Seismic ────────────────────────────────────────────────────────
        {
            "sensor_id": "BHA-SES-001", "name": "Seismic / Ice-Quake Sensor", "category": "seismic",
            "icon": "earthquake", "state": "online", "location": "Bedrock Anchor — West Arm",
            "parameters": [
                {"key": "ground_velocity",  "label": "Peak Ground Vel.", "value": 0.008,  "unit": "mm/s",  "normal_range": "<2 mm/s"},
                {"key": "frequency",        "label": "Dominant Freq.",   "value": 6.8,    "unit": "Hz",    "normal_range": "1–20 Hz"},
                {"key": "richter_est",      "label": "Est. Magnitude",   "value": 0.3,    "unit": "Ml",    "normal_range": "<2.0 Ml"},
                {"key": "event_count_24h",  "label": "Events (24 h)",    "value": 2,      "unit": "events","normal_range": "<5"},
            ],
        },
        {
            "sensor_id": "BHA-SES-002", "name": "Glacial Movement Sensor", "category": "seismic",
            "icon": "earthquake", "state": "offline", "location": "Ice Sheet Anchor — 500m NW",
            "parameters": [
                {"key": "ice_velocity",     "label": "Ice Sheet Velocity","value": 0.0,   "unit": "cm/day","normal_range": "0–50 cm/day"},
                {"key": "crack_depth",      "label": "Detected Crack Depth","value": 0.0, "unit": "m",     "normal_range": "N/A"},
                {"key": "gps_drift",        "label": "GPS Drift",         "value": 0.0,   "unit": "cm",    "normal_range": "<100 cm"},
                {"key": "tilt",             "label": "Tilt Angle",        "value": 0.0,   "unit": "°",     "normal_range": "<5 °"},
            ],
        },
        # ── Wildlife ───────────────────────────────────────────────────────
        {
            "sensor_id": "BHA-WLD-001", "name": "Penguin Colony Monitor", "category": "wildlife",
            "icon": "pets", "state": "online", "location": "Shore Perimeter — East Rookery",
            "parameters": [
                {"key": "detection_count",  "label": "Detections (24 h)","value": 42,     "unit": "events","normal_range": "0–200"},
                {"key": "closest_approach", "label": "Min Distance",     "value": 8.2,    "unit": "m",     "normal_range": ">5 m"},
                {"key": "acoustic_level",   "label": "Colony Noise",     "value": 52.8,   "unit": "dB",    "normal_range": "<80 dB"},
                {"key": "infrared_flux",    "label": "IR Flux (heat sig)","value": 1.48,  "unit": "W/m²",  "normal_range": ">0.05 W/m²"},
            ],
        },
        # ── Radiation ──────────────────────────────────────────────────────
        {
            "sensor_id": "BHA-RAD-001", "name": "UV / Solar Radiation Sensor", "category": "radiation",
            "icon": "wb_sunny", "state": "online", "location": "Roof Deck — South Aspect",
            "parameters": [
                {"key": "uv_index",         "label": "UV Index",         "value": 2.1,    "unit": "UVI",   "normal_range": "0–12 UVI"},
                {"key": "solar_irradiance", "label": "Solar Irradiance", "value": 488.0,  "unit": "W/m²",  "normal_range": "0–1400 W/m²"},
                {"key": "ozone_column",     "label": "Ozone Column",     "value": 284.0,  "unit": "DU",    "normal_range": "200–400 DU"},
                {"key": "uva_dose",         "label": "Daily UVA Dose",   "value": 0.64,   "unit": "kJ/m²", "normal_range": "<5 kJ/m²"},
            ],
        },
        # ── Meteorological ─────────────────────────────────────────────────
        {
            "sensor_id": "BHA-MET-001", "name": "Wind Speed & Direction", "category": "meteorological",
            "icon": "air", "state": "online", "location": "Met Mast — 10 m AGL",
            "parameters": [
                {"key": "wind_speed",       "label": "Wind Speed",       "value": 38.6,   "unit": "km/h",  "normal_range": "0–250 km/h"},
                {"key": "wind_direction",   "label": "Wind Direction",   "value": 312,    "unit": "°",     "normal_range": "0–360 °"},
                {"key": "gust_speed",       "label": "Peak Gust",        "value": 62.0,   "unit": "km/h",  "normal_range": "0–300 km/h"},
                {"key": "turbulence",       "label": "Turbulence Intens.","value": 0.24,  "unit": "TI",    "normal_range": "0–1"},
            ],
        },
        {
            "sensor_id": "BHA-MET-002", "name": "Snowfall & Blizzard Gauge", "category": "meteorological",
            "icon": "ac_unit", "state": "online", "location": "Station Perimeter — Open Field",
            "parameters": [
                {"key": "snowfall_rate",    "label": "Snowfall Rate",    "value": 2.4,    "unit": "mm/hr", "normal_range": "0–100 mm/hr"},
                {"key": "snow_depth",       "label": "Snow Depth",       "value": 218.0,  "unit": "cm",    "normal_range": "0–500 cm"},
                {"key": "visibility",       "label": "Visibility",       "value": 0.6,    "unit": "km",    "normal_range": "0–50 km"},
                {"key": "blizzard_risk",    "label": "Blizzard Risk",    "value": "HIGH",  "unit": "",      "normal_range": "LOW"},
            ],
        },
        # ── Structural ────────────────────────────────────────────────────
        {
            "sensor_id": "BHA-STR-001", "name": "Main Building Strain Gauge", "category": "structural",
            "icon": "foundation", "state": "online", "location": "Modular Frame — Junction J4",
            "parameters": [
                {"key": "strain",           "label": "Strain",           "value": 204,    "unit": "μϵ",    "normal_range": "<250 μϵ"},
                {"key": "settlement",       "label": "Foundation Settle.","value": 8.2,   "unit": "mm",    "normal_range": "<25 mm"},
                {"key": "snow_load",        "label": "Roof Snow Load",   "value": 4.8,    "unit": "kN/m²", "normal_range": "<6 kN/m²"},
                {"key": "temperature",      "label": "Frame Temp",       "value": -16.4,  "unit": "°C",    "normal_range": "-60 to 60 °C"},
            ],
        },
        # ── Air Quality ────────────────────────────────────────────────────
        {
            "sensor_id": "BHA-AQI-001", "name": "Indoor Air Quality Monitor", "category": "air_quality",
            "icon": "air", "state": "online", "location": "Main Lab — Section 3",
            "parameters": [
                {"key": "co2",              "label": "CO₂",              "value": 948,    "unit": "ppm",   "normal_range": "<1000 ppm"},
                {"key": "co",               "label": "CO",               "value": 3.2,    "unit": "ppm",   "normal_range": "<9 ppm"},
                {"key": "pm25",             "label": "PM2.5",            "value": 11.0,   "unit": "μg/m³", "normal_range": "<25 μg/m³"},
                {"key": "oxygen",           "label": "O₂ Concentration", "value": 20.8,   "unit": "%",     "normal_range": "19.5–23.5 %"},
            ],
        },
        # ── Ocean & Ice Monitoring ─────────────────────────────────────────
        {
            "sensor_id": "BHA-OCN-001", "name": "Sea Ice Thickness Sensor", "category": "oceanographic",
            "icon": "water", "state": "online", "location": "Jetty — Ice Monitoring Buoy",
            "parameters": [
                {"key": "ice_thickness",    "label": "Sea Ice Thickness","value": 182.0,  "unit": "cm",    "normal_range": ">50 cm (safe)"},
                {"key": "ice_temperature",  "label": "Ice Surface Temp", "value": -19.2,  "unit": "°C",    "normal_range": "<0 °C"},
                {"key": "wave_height",      "label": "Swell Height",     "value": 1.8,    "unit": "m",     "normal_range": "<5 m (safe ops)"},
                {"key": "tidal_level",      "label": "Tidal Level",      "value": 0.42,   "unit": "m",     "normal_range": "0–2 m"},
            ],
        },
        # ── Fire Safety ────────────────────────────────────────────────────
        {
            "sensor_id": "BHA-FIR-001", "name": "Smoke & Fire Detection Array", "category": "fire_safety",
            "icon": "local_fire_department", "state": "online", "location": "All Zones — Network",
            "parameters": [
                {"key": "smoke_density",    "label": "Smoke Density",    "value": 0.01,   "unit": "obs/m", "normal_range": "<0.1 obs/m"},
                {"key": "temp_rise_rate",   "label": "Temp Rise Rate",   "value": 0.0,    "unit": "°C/min","normal_range": "<8 °C/min"},
                {"key": "detectors_active", "label": "Detectors Online", "value": 48,     "unit": "/48",   "normal_range": "48/48"},
                {"key": "last_test",        "label": "Last System Test", "value": 8,      "unit": "days ago","normal_range": "<30 days"},
            ],
        },
        # ── Communications ─────────────────────────────────────────────────
        {
            "sensor_id": "BHA-COM-001", "name": "VSAT Link Quality Monitor", "category": "communications",
            "icon": "satellite_alt", "state": "online", "location": "Antenna Farm — VSAT Dish 1",
            "parameters": [
                {"key": "signal_strength",  "label": "Signal Strength",  "value": 14.2,   "unit": "dB",    "normal_range": ">5 dB"},
                {"key": "latency",          "label": "Round-trip Latency","value": 780,    "unit": "ms",    "normal_range": "<1500 ms"},
                {"key": "bandwidth",        "label": "Bandwidth",         "value": 4.8,    "unit": "Mbps",  "normal_range": ">0.5 Mbps"},
                {"key": "packet_loss",      "label": "Packet Loss",       "value": 0.1,    "unit": "%",     "normal_range": "<2 %"},
            ],
        },
    ],
}

_IOT_CATEGORIES = [
    {"key": "temperature",     "label": "Temperature",           "icon": "thermostat"},
    {"key": "pressure",        "label": "Pressure",              "icon": "compress"},
    {"key": "fuel",            "label": "Fuel Monitoring",       "icon": "local_gas_station"},
    {"key": "seismic",         "label": "Seismic / Glacial",     "icon": "earthquake"},
    {"key": "wildlife",        "label": "Wildlife & Ecology",    "icon": "pets"},
    {"key": "radiation",       "label": "UV & Radiation",        "icon": "wb_sunny"},
    {"key": "meteorological",  "label": "Meteorological",        "icon": "air"},
    {"key": "structural",      "label": "Structural Integrity",  "icon": "foundation"},
    {"key": "air_quality",     "label": "Air Quality",           "icon": "air"},
    {"key": "oceanographic",   "label": "Oceanographic",         "icon": "water"},
    {"key": "fire_safety",     "label": "Fire & Safety",         "icon": "local_fire_department"},
    {"key": "communications",  "label": "Communications",        "icon": "satellite_alt"},
]


@router.get("/iot/sensors")
async def get_iot_sensors(
    station_id: Optional[str] = Query(None, description="Filter: maitri or bharati"),
    category: Optional[str] = Query(None, description="Filter by sensor category"),
    state: Optional[str] = Query(None, description="Filter: online or offline"),
) -> dict:
    """Return hardcoded IoT sensor registry for Antarctic stations.

    Each sensor includes its current state (online/offline) and 3–4
    governing operational parameters with current readings, units, and
    normal operating ranges.  Intended for the IoT Tracking page and
    linkable to Maitri/Bharati dashboards once they are built.
    """
    if station_id and station_id.lower() in _IOT_SENSORS:
        sensors = _IOT_SENSORS[station_id.lower()]
        if category:
            sensors = [s for s in sensors if s["category"] == category.lower()]
        if state:
            sensors = [s for s in sensors if s["state"] == state.lower()]
        return {
            "station_id": station_id.lower(),
            "sensors": sensors,
            "total": len(sensors),
            "online": sum(1 for s in sensors if s["state"] == "online"),
            "offline": sum(1 for s in sensors if s["state"] == "offline"),
            "categories": _IOT_CATEGORIES,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_source": "hardcoded_v1",
        }
    # Both stations
    all_sensors = {sid: lst for sid, lst in _IOT_SENSORS.items()}
    return {
        "stations": all_sensors,
        "categories": _IOT_CATEGORIES,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "hardcoded_v1",
    }


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


@router.get("/stations/{station_id}/assets", response_model=List[AssetOut])
async def get_assets(
    station_id: str,
    asset_type: Optional[str] = Query(None, description="Filter by asset_type"),
    session: AsyncSession = Depends(get_db_session),
) -> List[AssetOut]:
    """Return all infrastructure assets for a station."""
    q = select(Asset).where(Asset.station_id == station_id)
    if asset_type:
        q = q.where(Asset.asset_type == asset_type.lower())
    q = q.order_by(Asset.asset_type, Asset.name)
    rows = (await session.execute(q)).scalars().all()
    return [AssetOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Resupply Manifests
# ---------------------------------------------------------------------------

@router.get("/resupply", response_model=List[ResupplyManifestOut])
async def get_resupply(
    station_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_session),
) -> List[ResupplyManifestOut]:
    """Return resupply manifests with their line items, newest first."""
    q = select(ResupplyManifest).order_by(ResupplyManifest.voyage_year.desc())
    if station_id:
        q = q.where(ResupplyManifest.station_id == station_id)

    manifests = (await session.execute(q)).scalars().all()
    result = []
    for m in manifests:
        items_result = await session.execute(
            select(ResupplyLineItem).where(ResupplyLineItem.manifest_id == m.manifest_id)
        )
        line_items = items_result.scalars().all()
        result.append(ResupplyManifestOut(
            manifest_id=m.manifest_id,
            station_id=m.station_id,
            expedition_name=m.expedition_name,
            voyage_year=m.voyage_year,
            ship_name=m.ship_name,
            departure_date=m.departure_date,
            arrival_window_start=m.arrival_window_start,
            arrival_window_end=m.arrival_window_end,
            status=m.status,
            notes=m.notes,
            line_items=[ResupplyLineItemOut.model_validate(li) for li in line_items],
        ))
    return result


# ---------------------------------------------------------------------------
# AI Predictions
# ---------------------------------------------------------------------------

@router.get("/stations/{station_id}/predictions", response_model=List[AIPredictionOut])
async def get_predictions(
    station_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> List[AIPredictionOut]:
    """Return AI predictions for a station, newest first."""
    rows = (await session.execute(
        select(AIPrediction)
        .where(AIPrediction.station_id == station_id)
        .order_by(AIPrediction.generated_at.desc())
        .limit(20)
    )).scalars().all()
    return [AIPredictionOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@router.get("/report")
async def get_report(
    station_id: Optional[str] = Query(None, description="maitri | bharati | None for both"),
    report_type: str = Query("daily", description="daily | monthly | incident | scientific | audit"),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    Generate a structured report from live DB data.
    Returns JSON with alerts, sensor readings, inventory, assets and station status.
    """
    cfg = get_config()
    station_ids = [station_id] if station_id else cfg.station_ids

    # --- Station status --------------------------------------------------
    station_rows = (await session.execute(select(StationConnection))).scalars().all()
    stations_info = {
        r.station_id: {
            "station_id": r.station_id,
            "display_name": _station_display(r.station_id),
            "link_state": r.link_state,
            "open_critical_alerts": r.open_critical_alerts or 0,
            "open_high_alerts": r.open_high_alerts or 0,
            "services_healthy": r.services_healthy,
        }
        for r in station_rows
    }

    # --- Alerts (last 30 days) -------------------------------------------
    cutoff_30d = utcnow() - timedelta(days=30)
    alert_q = select(Alert).where(Alert.triggered_at >= cutoff_30d)
    if station_id:
        alert_q = alert_q.where(Alert.station_id == station_id)
    alert_q = alert_q.order_by(Alert.triggered_at.desc()).limit(50)
    alerts = (await session.execute(alert_q)).scalars().all()

    alert_counts: dict = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for a in alerts:
        alert_counts[a.severity] = alert_counts.get(a.severity, 0) + 1

    # --- Sensor summary (latest per sensor, 7d window) -------------------
    cutoff_7d = utcnow() - timedelta(days=7)
    cutoff_24h = utcnow() - timedelta(hours=24)

    sensor_data = {}
    for sid in station_ids:
        latest_subq = (
            select(SensorReading.sensor_id, func.max(SensorReading.timestamp_utc).label("max_ts"))
            .where(SensorReading.station_id == sid)
            .where(SensorReading.timestamp_utc >= cutoff_7d)
            .group_by(SensorReading.sensor_id)
            .subquery()
        )
        rows = (await session.execute(
            select(SensorReading)
            .join(latest_subq,
                  (SensorReading.sensor_id == latest_subq.c.sensor_id)
                  & (SensorReading.timestamp_utc == latest_subq.c.max_ts))
        )).scalars().all()
        count_24h = (await session.execute(
            select(func.count(SensorReading.id))
            .where(SensorReading.station_id == sid)
            .where(SensorReading.timestamp_utc >= cutoff_24h)
        )).scalar_one() or 0
        sensor_data[sid] = {
            "readings_24h": count_24h,
            "latest": [
                {"sensor_id": r.sensor_id, "domain": r.domain, "value": r.value,
                 "unit": r.unit, "ts": r.timestamp_utc.isoformat()}
                for r in rows
            ],
        }

    # --- Inventory --------------------------------------------------------
    inv_data = {}
    for sid in station_ids:
        rows = (await session.execute(
            select(InventoryItem).where(InventoryItem.station_id == sid)
            .order_by(InventoryItem.category)
        )).scalars().all()
        inv_data[sid] = [
            {"name": r.name, "category": r.category, "quantity": r.quantity,
             "unit": r.unit, "days_remaining": r.days_remaining,
             "status": _compute_inventory_status(r)}
            for r in rows
        ]

    # --- Assets -----------------------------------------------------------
    asset_data = {}
    for sid in station_ids:
        rows = (await session.execute(
            select(Asset).where(Asset.station_id == sid)
        )).scalars().all()
        asset_data[sid] = [
            {"name": r.name, "asset_type": r.asset_type, "status": r.status}
            for r in rows
        ]

    return {
        "report_type": report_type,
        "generated_at": utcnow().isoformat(),
        "station_ids": station_ids,
        "stations": stations_info,
        "alert_summary": {
            "counts_by_severity": alert_counts,
            "total_last_30d": len(alerts),
            "recent": [
                {"alert_id": a.alert_id, "severity": a.severity, "domain": a.domain,
                 "description": a.description, "triggered_at": a.triggered_at.isoformat(),
                 "ack_state": a.ack_state}
                for a in alerts[:10]
            ],
        },
        "sensor_summary": sensor_data,
        "inventory": inv_data,
        "assets": asset_data,
    }


@router.get("/report/download")
async def download_report(
    station_id: Optional[str] = Query(None),
    report_type: str = Query("daily"),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    Generate a downloadable plain-text report from live DB data.
    Returns a JSON with { filename, content } — frontend triggers blob download.
    """
    from fastapi.responses import PlainTextResponse

    cfg = get_config()
    station_ids = [station_id] if station_id else cfg.station_ids
    now = utcnow()

    # Fetch all needed data via the same report endpoint logic
    station_rows = (await session.execute(select(StationConnection))).scalars().all()
    station_map = {r.station_id: r for r in station_rows}

    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    lines = []
    sep = "=" * 72
    dash = "-" * 72

    lines.append(sep)
    lines.append("  VAJRAX — NCPOR ANTARCTIC STATION MONITORING SYSTEM")
    lines.append(f"  Report Type : {report_type.upper()}")
    lines.append(f"  Generated   : {now.strftime('%d %b %Y  %H:%M:%S UTC')}")
    lines.append(f"  Stations    : {', '.join(s.upper() for s in station_ids)}")
    lines.append(f"  Classification: OFFICIAL")
    lines.append(sep)

    for sid in station_ids:
        conn = station_map.get(sid)
        lines.append("")
        lines.append(f"  STATION: {sid.upper()} — {_station_display(sid)}")
        lines.append(dash)

        # Station status
        if conn:
            lines.append(f"  Link State        : {conn.link_state}")
            lines.append(f"  Open Critical     : {conn.open_critical_alerts or 0}")
            lines.append(f"  Open High         : {conn.open_high_alerts or 0}")
            lines.append(f"  Services Healthy  : {conn.services_healthy}")
        else:
            lines.append("  Status: NO CONNECTION DATA")

        # Sensors
        lines.append("")
        lines.append("  SENSOR READINGS (Latest)")
        lines.append("  " + "-" * 50)
        latest_subq = (
            select(SensorReading.sensor_id, func.max(SensorReading.timestamp_utc).label("max_ts"))
            .where(SensorReading.station_id == sid)
            .where(SensorReading.timestamp_utc >= cutoff_7d)
            .group_by(SensorReading.sensor_id)
            .subquery()
        )
        sensor_rows = (await session.execute(
            select(SensorReading)
            .join(latest_subq,
                  (SensorReading.sensor_id == latest_subq.c.sensor_id)
                  & (SensorReading.timestamp_utc == latest_subq.c.max_ts))
            .order_by(SensorReading.domain)
        )).scalars().all()

        cur_domain = ""
        for r in sensor_rows:
            if r.domain != cur_domain:
                lines.append(f"  [{r.domain.upper()}]")
                cur_domain = r.domain
            metric = r.sensor_id.rsplit(".", 1)[-1]
            lines.append(f"    {metric:30} {r.value:10.3f}  {r.unit}")

        if not sensor_rows:
            lines.append("  No recent sensor data.")

        # Alerts
        lines.append("")
        lines.append("  ALERTS — Last 30 Days")
        lines.append("  " + "-" * 50)
        alert_q = (
            select(Alert)
            .where(Alert.station_id == sid)
            .where(Alert.triggered_at >= cutoff_30d)
            .order_by(Alert.triggered_at.desc())
            .limit(20)
        )
        alert_rows = (await session.execute(alert_q)).scalars().all()
        sev_counts: dict = {}
        for a in alert_rows:
            sev_counts[a.severity] = sev_counts.get(a.severity, 0) + 1
        for sev, cnt in sorted(sev_counts.items()):
            lines.append(f"    {sev:12} : {cnt}")
        lines.append("")
        for a in alert_rows[:8]:
            ts = a.triggered_at.strftime("%d-%b %H:%M")
            lines.append(f"    [{a.severity:8}] {ts}  {a.description[:55]}")

        if not alert_rows:
            lines.append("  No alerts in last 30 days.")

        # Inventory
        lines.append("")
        lines.append("  INVENTORY STATUS")
        lines.append("  " + "-" * 50)
        inv_rows = (await session.execute(
            select(InventoryItem)
            .where(InventoryItem.station_id == sid)
            .order_by(InventoryItem.category)
        )).scalars().all()
        for i in inv_rows:
            status = _compute_inventory_status(i)
            flag = "⚠" if status != "NOMINAL" else " "
            lines.append(f"  {flag} {i.name[:42]:42} {i.quantity:10.1f}  {i.unit:10}  [{status}]")

        if not inv_rows:
            lines.append("  No inventory data.")

        # Assets
        lines.append("")
        lines.append("  ASSETS / INFRASTRUCTURE")
        lines.append("  " + "-" * 50)
        asset_rows = (await session.execute(
            select(Asset).where(Asset.station_id == sid).order_by(Asset.asset_type)
        )).scalars().all()
        for a in asset_rows:
            lines.append(f"  {a.asset_type:20}  {a.name:40}  {a.status}")

        if not asset_rows:
            lines.append("  No asset data.")

    lines.append("")
    lines.append(sep)
    lines.append("  END OF REPORT  —  VajraX Digital Twin Platform  —  NCPOR / MoES")
    lines.append(sep)

    content = "\n".join(lines)
    filename = f"VajraX_{report_type}_{now.strftime('%Y%m%d_%H%M%S')}.txt"

    return {"filename": filename, "content": content}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "service": "cloud-hq-api", "version": "1.0.0"}
