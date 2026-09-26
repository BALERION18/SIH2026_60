#!/usr/bin/env python3
"""
VajraX — Direct Neon Database Init + Seed (No Alembic)
========================================================
Creates all tables using SQLAlchemy metadata.create_all() and inserts
rich dummy data for the frontend dashboard demo.

Usage (from project root):
    PYTHONPATH=. python scripts/init_db.py

Requirements: .env must be populated with CLOUD_DATABASE_URL
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── load .env ─────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env", override=True)
except ImportError:
    pass  # env vars must be set in shell

# ── colour helpers ─────────────────────────────────────────────────────────────
G, R, Y, C, B, E = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
def ok(m):  print(f"  {G}✓{E} {m}")
def fail(m): print(f"  {R}✗{E} {m}")
def info(m): print(f"  {C}→{E} {m}")
def hdr(m):  print(f"\n{B}{C}{m}{E}")


def _now() -> datetime:
    return datetime.now(timezone.utc)

def _uid() -> str:
    return str(uuid.uuid4())

def _ago(hours=0, minutes=0, days=0) -> datetime:
    return _now() - timedelta(hours=hours, minutes=minutes, days=days)


async def main() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import text, select

    db_url = os.environ.get("CLOUD_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        fail("CLOUD_DATABASE_URL not set. Add it to .env")
        sys.exit(1)

    # Neon pooler requires SSL; asyncpg needs ssl=True in connect_args,
    # not sslmode in the query string
    import re
    db_url = re.sub(r"[?&]sslmode=[^&]*", "", db_url)
    db_url = re.sub(r"[?&]channel_binding=[^&]*", "", db_url)
    db_url = re.sub(r"[?&]+$", "", db_url)  # trailing ? or &

    host = db_url.split("@")[-1] if "@" in db_url else "…"
    info(f"Connecting to: {host}")

    connect_args = {}
    if "neon.tech" in db_url:
        import ssl as _ssl
        ctx = _ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = _ssl.CERT_REQUIRED
        connect_args["ssl"] = ctx

    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True,
                                  pool_size=2, max_overflow=3, pool_recycle=300,
                                  connect_args=connect_args)

    # ── Import ALL models so metadata is populated ──────────────────────────
    from shared.db.base import Base
    from shared.db.models.cloud import (   # noqa: F401
        Asset, MaintenanceEvent, ResupplyManifest, ResupplyLineItem,
        AIPrediction, StationConnection, StationConfig, User, Role, UserRole,
    )
    from shared.db.models.edge import (    # noqa: F401
        SensorReading, Alert, OutboundQueueItem, BlackBoxFrame,
        InventoryItem, AssetCache, AuditLogEntry, LinkStatusRecord,
    )

    # ── CREATE ALL TABLES ───────────────────────────────────────────────────
    hdr("1/5  Creating all tables…")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    ok("All tables created / verified")

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:

        # ── ROLES ───────────────────────────────────────────────────────────
        hdr("2/5  Seeding roles, users, and RBAC…")

        existing_roles = (await db.execute(text("SELECT role_name FROM roles"))).fetchall()
        existing_role_names = {r[0] for r in existing_roles}

        role_map: dict[str, str] = {}
        for rname, rdesc in [
            ("ADMIN",         "Full platform access — manage users, stations, configuration."),
            ("OPERATOR",      "Operational access — acknowledge alerts, update inventory."),
            ("STATION_CREW",  "On-station crew — limited to their assigned station."),
            ("VIEWER",        "Read-only access to dashboards and reports."),
        ]:
            if rname not in existing_role_names:
                rid = _uid()
                await db.execute(text(
                    "INSERT INTO roles (role_id, role_name, description) "
                    "VALUES (:id, :name, :desc)"
                ), {"id": rid, "name": rname, "desc": rdesc})
                role_map[rname] = rid
                ok(f"Role: {rname}")
            else:
                row = (await db.execute(text(
                    "SELECT role_id FROM roles WHERE role_name=:n"), {"n": rname})).fetchone()
                role_map[rname] = row[0]

        # Users
        existing_users = {r[0] for r in (await db.execute(text("SELECT username FROM users"))).fetchall()}

        users_to_seed = [
            ("admin",    "admin123",    "admin@vajrax.ncpor.in",   "ADMIN"),
            ("operator1","operator123", "ops1@vajrax.ncpor.in",    "OPERATOR"),
            ("crew_maitri","crew123",   "crew.maitri@ncpor.in",    "STATION_CREW"),
            ("viewer",   "viewer123",   "viewer@vajrax.ncpor.in",  "VIEWER"),
        ]

        from passlib.context import CryptContext
        pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

        user_map: dict[str, str] = {}
        for uname, pwd, email, role_name in users_to_seed:
            if uname not in existing_users:
                uid = _uid()
                hashed = pwd_ctx.hash(pwd)
                await db.execute(text(
                    "INSERT INTO users (user_id, username, email, hashed_password, is_active, created_at) "
                    "VALUES (:id, :un, :em, :hp, true, :ca)"
                ), {"id": uid, "un": uname, "em": email, "hp": hashed, "ca": _now()})
                await db.execute(text(
                    "INSERT INTO user_roles (assignment_id, user_id, role_id, station_scope, assigned_at, assigned_by) "
                    "VALUES (:aid, :uid, :rid, NULL, :at, 'system')"
                ), {"aid": _uid(), "uid": uid, "rid": role_map[role_name], "at": _now()})
                user_map[uname] = uid
                ok(f"User: {uname} / {pwd}  [{role_name}]")
            else:
                row = (await db.execute(text(
                    "SELECT user_id FROM users WHERE username=:u"), {"u": uname})).fetchone()
                user_map[uname] = row[0]

        await db.commit()

        # ── STATION CONNECTIONS ─────────────────────────────────────────────
        hdr("3/5  Seeding station connections…")

        for sid, state, crit, high, healthy, qbytes, hb_offset_min in [
            ("maitri",  "UP",       2, 3, True,  245760,  2),
            ("bharati", "DEGRADED", 1, 1, True,  819200,  8),
        ]:
            await db.execute(text("""
                INSERT INTO station_connections
                    (station_id, last_heartbeat_at, link_state, queue_depth_bytes,
                     open_critical_alerts, open_high_alerts, services_healthy, updated_at)
                VALUES (:sid, :hb, :ls, :qd, :oc, :oh, :sh, :ua)
                ON CONFLICT (station_id) DO UPDATE SET
                    last_heartbeat_at = EXCLUDED.last_heartbeat_at,
                    link_state        = EXCLUDED.link_state,
                    queue_depth_bytes = EXCLUDED.queue_depth_bytes,
                    open_critical_alerts = EXCLUDED.open_critical_alerts,
                    open_high_alerts  = EXCLUDED.open_high_alerts,
                    services_healthy  = EXCLUDED.services_healthy,
                    updated_at        = EXCLUDED.updated_at
            """), {
                "sid": sid, "ls": state, "qd": qbytes,
                "oc": crit, "oh": high, "sh": healthy,
                "hb": _ago(minutes=hb_offset_min), "ua": _now(),
            })
            ok(f"Station: {sid} → {state}")

        await db.commit()

        # ── ASSETS ─────────────────────────────────────────────────────────
        hdr("4/5  Seeding infrastructure assets…")

        assets_data = [
            # Maitri assets
            ("maitri.generator.gen1", "maitri", "GENERATOR",   "Maitri Diesel Generator #1",       -70.7671, 11.7328, 117.0, "ACTIVE",            '{"fuel_type":"diesel","rated_kw":100,"hours_run":14250}'),
            ("maitri.generator.gen2", "maitri", "GENERATOR",   "Maitri Diesel Generator #2",       -70.7672, 11.7330, 117.0, "UNDER_MAINTENANCE",  '{"fuel_type":"diesel","rated_kw":100,"hours_run":9870}'),
            ("maitri.power.grid",     "maitri", "POWER_GRID",  "Maitri Station Power Distribution",-70.7671, 11.7329, 117.0, "ACTIVE",            '{"phases":3,"voltage_v":415}'),
            ("maitri.weather.aws1",   "maitri", "SENSOR_NODE", "Maitri Automatic Weather Station", -70.7680, 11.7340, 119.0, "ACTIVE",            '{"sensors":["temperature","wind_speed","wind_dir","pressure","humidity"]}'),
            ("maitri.building.main",  "maitri", "BUILDING",    "Maitri Main Living Block",         -70.7670, 11.7325, 117.0, "ACTIVE",            '{"floors":2,"capacity":25}'),
            ("maitri.building.lab",   "maitri", "BUILDING",    "Maitri Science Laboratory",        -70.7673, 11.7332, 117.5, "ACTIVE",            '{"labs":["glaciology","meteorology","seismology"]}'),
            ("maitri.tank.fuel_main", "maitri", "FUEL_TANK",   "Maitri Main Fuel Storage Tank",    -70.7665, 11.7318, 116.5, "ACTIVE",            '{"capacity_litres":200000,"fuel_type":"diesel","current_pct":68.4}'),
            ("maitri.seismic.sta1",   "maitri", "SENSOR_NODE", "Maitri Seismic Monitoring Station",-70.7690, 11.7350, 120.0, "ACTIVE",            '{"sensors":["seismic_x","seismic_y","seismic_z"]}'),
            # Bharati assets
            ("bharati.generator.gen1","bharati","GENERATOR",   "Bharati Diesel Generator #1",      -69.4072, 76.1929,  35.0, "ACTIVE",            '{"fuel_type":"diesel","rated_kw":160,"hours_run":8320}'),
            ("bharati.generator.gen2","bharati","GENERATOR",   "Bharati Diesel Generator #2",      -69.4073, 76.1932,  35.0, "ACTIVE",            '{"fuel_type":"diesel","rated_kw":160,"hours_run":8190}'),
            ("bharati.solar.array1",  "bharati","SOLAR_ARRAY", "Bharati Solar Panel Array",        -69.4060, 76.1915,  34.0, "ACTIVE",            '{"panels":48,"rated_kwp":12,"efficiency_pct":21.3}'),
            ("bharati.weather.aws1",  "bharati","SENSOR_NODE", "Bharati Automatic Weather Station",-69.4085, 76.1945,  36.0, "ACTIVE",            '{"sensors":["temperature","wind_speed","wind_dir","pressure","humidity","radiation"]}'),
            ("bharati.building.main", "bharati","BUILDING",    "Bharati Main Research Building",   -69.4072, 76.1928,  35.0, "ACTIVE",            '{"floors":3,"capacity":47}'),
            ("bharati.building.lab",  "bharati","BUILDING",    "Bharati Science Laboratory Wing",  -69.4075, 76.1935,  35.5, "ACTIVE",            '{"labs":["oceanography","glaciology","atmospheric"]}'),
            ("bharati.tank.fuel_main","bharati","FUEL_TANK",   "Bharati Main Fuel Storage Tank",   -69.4065, 76.1920,  34.5, "ACTIVE",            '{"capacity_litres":350000,"fuel_type":"diesel","current_pct":54.1}'),
            ("bharati.antenna.vsat",  "bharati","ANTENNA",     "Bharati VSAT Satellite Antenna",   -69.4068, 76.1922,  36.0, "ACTIVE",            '{"bandwidth_mhz":4,"protocol":"DVB-S2","provider":"ISRO"}'),
        ]

        existing_assets = {r[0] for r in (await db.execute(text("SELECT asset_id FROM assets"))).fetchall()}
        for a in assets_data:
            if a[0] not in existing_assets:
                await db.execute(text("""
                    INSERT INTO assets
                        (asset_id, station_id, asset_type, name, latitude, longitude,
                         elevation_m, status, metadata_json, commissioned_at, created_at, updated_at)
                    VALUES (:id, :sid, :typ, :nm, :lat, :lon, :elev, :st, CAST(:mj AS jsonb), :ca, :cr, :ua)
                """), {
                    "id": a[0], "sid": a[1], "typ": a[2], "nm": a[3],
                    "lat": a[4], "lon": a[5], "elev": a[6], "st": a[7], "mj": a[8],
                    "ca": _ago(days=365), "cr": _ago(days=365), "ua": _now(),
                })
        await db.commit()
        ok(f"Assets: {len(assets_data)} total")

        # ── SENSOR READINGS (rich time-series data) ─────────────────────────
        hdr("5/5  Seeding sensor readings, alerts & inventory…")

        import math, random
        random.seed(42)

        def wave(base, amp, i, period=60): return base + amp * math.sin(2*math.pi*i/period)
        def jitter(v, pct=0.03): return v * (1 + random.uniform(-pct, pct))

        # Define sensors per station
        sensor_defs = {
            "maitri": [
                ("maitri.weather.aws1.temperature", "weather", "temperature", "°C",  -22.0,  4.0),
                ("maitri.weather.aws1.wind_speed",  "weather", "wind_speed",  "km/h",  38.0, 12.0),
                ("maitri.weather.aws1.wind_dir",    "weather", "wind_dir",    "°",    247.0,  8.0),
                ("maitri.weather.aws1.pressure",    "weather", "pressure",    "hPa",  985.0,  3.0),
                ("maitri.weather.aws1.humidity",    "weather", "humidity",    "%",     72.0,  8.0),
                ("maitri.generator.gen1.kw_output", "energy",  "kw_output",   "kW",    78.0,  9.0),
                ("maitri.generator.gen1.fuel_pct",  "energy",  "fuel_pct",    "%",     68.4,  0.1),
                ("maitri.generator.gen1.load_pct",  "energy",  "load_pct",    "%",     78.0,  5.0),
                ("maitri.power.grid.voltage",       "energy",  "voltage",     "V",    415.0,  5.0),
                ("maitri.seismic.sta1.pgv",         "seismic", "pgv",         "mm/s",   0.02, 0.01),
                ("maitri.seismic.sta1.magnitude",   "seismic", "magnitude",   "ML",     0.8,  0.3),
                ("maitri.weather.aws1.snowfall",    "weather", "snowfall",    "mm/h",   2.1,  1.0),
            ],
            "bharati": [
                ("bharati.weather.aws1.temperature","weather", "temperature", "°C",  -11.0,  3.0),
                ("bharati.weather.aws1.wind_speed", "weather", "wind_speed",  "km/h",  52.0, 15.0),
                ("bharati.weather.aws1.wind_dir",   "weather", "wind_dir",    "°",    195.0, 10.0),
                ("bharati.weather.aws1.pressure",   "weather", "pressure",    "hPa",  978.0,  4.0),
                ("bharati.weather.aws1.humidity",   "weather", "humidity",    "%",     81.0,  6.0),
                ("bharati.generator.gen1.kw_output","energy",  "kw_output",   "kW",   124.0, 12.0),
                ("bharati.generator.gen1.fuel_pct", "energy",  "fuel_pct",    "%",     54.1,  0.1),
                ("bharati.generator.gen1.load_pct", "energy",  "load_pct",    "%",     77.5,  6.0),
                ("bharati.solar.array1.kw_output",  "energy",  "kw_output",   "kW",     6.8,  2.0),
                ("bharati.power.grid.voltage",      "energy",  "voltage",     "V",    415.0,  5.0),
                ("bharati.weather.aws1.radiation",  "weather", "radiation",   "W/m²",  310.0, 40.0),
                ("bharati.weather.aws1.snowfall",   "weather", "snowfall",    "mm/h",   0.4,  0.3),
            ],
        }

        # Insert 288 readings per sensor (24h at 5-min intervals)
        total_inserted = 0
        INTERVAL_MINUTES = 5
        POINTS = 288  # 24 hours

        # Check existing readings to avoid duplicate inserts
        existing_count = (await db.execute(text("SELECT COUNT(*) FROM sensor_readings"))).scalar()
        if existing_count and existing_count > 100:
            ok(f"Sensor readings already exist ({existing_count} rows) — skipping bulk insert")
        else:
            batch = []
            for station_id, sensors in sensor_defs.items():
                for i in range(POINTS):
                    ts = _ago(minutes=(POINTS - i) * INTERVAL_MINUTES)
                    for sensor_id, domain, metric, unit, base, amp in sensors:
                        val = jitter(wave(base, amp, i))
                        batch.append({
                            "sid": station_id, "seid": sensor_id, "dom": domain,
                            "mn": metric, "val": round(val, 3), "un": unit,
                            "ts": ts, "qual": "NOMINAL", "aid": sensor_id.rsplit(".", 1)[0],
                        })
                        if len(batch) >= 500:
                            await db.execute(text("""
                                INSERT INTO sensor_readings
                                    (station_id, sensor_id, domain, metric_name, value,
                                     unit, quality, asset_id, timestamp_utc, is_aggregate)
                                VALUES (:sid, :seid, :dom, :mn, :val, :un, :qual, :aid, :ts, false)
                            """), batch)
                            total_inserted += len(batch)
                            batch = []
            if batch:
                await db.execute(text("""
                    INSERT INTO sensor_readings
                        (station_id, sensor_id, domain, metric_name, value,
                         unit, quality, asset_id, timestamp_utc, is_aggregate)
                    VALUES (:sid, :seid, :dom, :mn, :val, :un, :qual, :aid, :ts, false)
                """), batch)
                total_inserted += len(batch)
            await db.commit()
            ok(f"Sensor readings: {total_inserted} rows inserted")

        # ── ALERTS ──────────────────────────────────────────────────────────
        existing_alerts = (await db.execute(text("SELECT COUNT(*) FROM alerts"))).scalar() or 0
        if existing_alerts < 5:
            alerts_seed = [
                # (alert_id, station_id, severity, domain, asset_id, description, ack_state, minutes_ago, black_box)
                ("maitri-energy-001", "maitri", "CRITICAL", "energy", "maitri.generator.gen2",
                 "Generator #2 Fault — Automatic Shutdown Triggered", "OPEN", 45, True),
                ("maitri-energy-002", "maitri", "HIGH",     "energy", "maitri.tank.fuel_main",
                 "Fuel Tank Level Below 70% Threshold — Resupply Advisory", "OPEN", 120, False),
                ("maitri-weather-001","maitri", "HIGH",     "weather","maitri.weather.aws1",
                 "Wind Speed Exceeding 60 km/h — Outdoor Operations Suspended", "ACKNOWLEDGED", 180, False),
                ("maitri-energy-003", "maitri", "MEDIUM",   "energy", "maitri.power.grid",
                 "Grid Voltage Fluctuation Detected — ±8% Variation", "OPEN", 30, False),
                ("bharati-energy-001","bharati","CRITICAL","energy",  "bharati.generator.gen1",
                 "Generator #1 Overload — Load Shedding Initiated", "OPEN", 15, True),
                ("bharati-weather-001","bharati","HIGH",   "weather", "bharati.weather.aws1",
                 "Blizzard Warning — Wind Speed 87 km/h, Visibility <50m", "OPEN", 60, False),
                ("bharati-energy-002","bharati","MEDIUM",  "energy",  "bharati.tank.fuel_main",
                 "Bharati Fuel Reserve Below 60% — 127 Days Until Critical", "ACKNOWLEDGED", 240, False),
                ("maitri-seismic-001","maitri","LOW",     "seismic",  "maitri.seismic.sta1",
                 "Micro-seismic Activity ML 1.2 Recorded — Monitoring", "RESOLVED", 300, False),
                ("bharati-weather-002","bharati","LOW",   "weather",  "bharati.weather.aws1",
                 "Atmospheric Pressure Drop 12 hPa in 3h — Monitoring", "OPEN", 90, False),
                ("maitri-energy-004", "maitri", "MEDIUM", "energy",  "maitri.generator.gen1",
                 "Generator #1 Running >72h Continuous — Scheduled Maintenance Due", "OPEN", 20, False),
            ]

            for a in alerts_seed:
                aid, sid, sev, dom, asset, desc, ack, mins, bb = a
                ack_by  = "ops.controller@ncpor.in" if ack == "ACKNOWLEDGED" else None
                ack_at  = _ago(minutes=mins-30) if ack == "ACKNOWLEDGED" else None
                res_at  = _ago(minutes=mins-60) if ack == "RESOLVED" else None
                await db.execute(text("""
                    INSERT INTO alerts
                        (alert_id, station_id, severity, domain, asset_id, description,
                         triggered_at, ack_state, acknowledged_by, acknowledged_at,
                         resolved_at, black_box_activated, synced_to_cloud, created_at)
                    VALUES
                        (:aid, :sid, :sev, :dom, :ast, :desc,
                         :trig, :ack, :ab, :aa,
                         :ra, :bb, true, :ca)
                    ON CONFLICT (alert_id) DO NOTHING
                """), {
                    "aid": aid, "sid": sid, "sev": sev, "dom": dom, "ast": asset,
                    "desc": desc, "trig": _ago(minutes=mins),
                    "ack": ack, "ab": ack_by, "aa": ack_at,
                    "ra": res_at, "bb": bb, "ca": _ago(minutes=mins),
                })
            await db.commit()
            ok(f"Alerts: {len(alerts_seed)} seeded")

        # ── INVENTORY ───────────────────────────────────────────────────────
        existing_inv = (await db.execute(text("SELECT COUNT(*) FROM inventory_items"))).scalar() or 0
        if existing_inv < 5:
            inventory_seed = [
                # (item_id, station_id, category, name, qty, unit, min_thresh, burn_rate)
                ("maitri.fuel.diesel_main",  "maitri",  "FUEL",       "Diesel Fuel (Main Reserve)",    136800, "litres", 40000, 530.0),
                ("maitri.fuel.aviation",     "maitri",  "FUEL",       "Aviation Turbine Fuel (ATF)",    12400, "litres",  3000,  48.0),
                ("maitri.food.dry_rations",  "maitri",  "FOOD",       "Dry Rations (2026 Stock)",        4800, "kg",       500,  19.2),
                ("maitri.medical.oxygen",    "maitri",  "MEDICAL",    "Medical Oxygen Cylinders",         42,  "units",    10,   0.15),
                ("maitri.parts.gen_filters", "maitri",  "SPARE_PARTS","Generator Air Filters",             8,  "units",     3,   0.05),
                ("maitri.parts.solar_inv",   "maitri",  "SPARE_PARTS","Solar Inverter (Spare)",            2,  "units",     1,   0.0),
                ("maitri.food.frozen",       "maitri",  "FOOD",       "Frozen Food Stock",               2100, "kg",      300,   8.4),
                ("maitri.medical.first_aid", "maitri",  "MEDICAL",    "First Aid Kits",                    18, "units",     5,   0.05),
                ("bharati.fuel.diesel_main", "bharati", "FUEL",       "Diesel Fuel (Main Reserve)",    189350, "litres", 70000, 780.0),
                ("bharati.fuel.aviation",    "bharati", "FUEL",       "Aviation Turbine Fuel (ATF)",    18200, "litres",  4000,  72.0),
                ("bharati.food.dry_rations", "bharati", "FOOD",       "Dry Rations (2026 Stock)",        9200, "kg",      900,  36.8),
                ("bharati.medical.oxygen",   "bharati", "MEDICAL",    "Medical Oxygen Cylinders",         78,  "units",    20,   0.28),
                ("bharati.parts.gen_filters","bharati", "SPARE_PARTS","Generator Air Filters",            12,  "units",     4,   0.08),
                ("bharati.parts.pump_seal",  "bharati", "SPARE_PARTS","Hydraulic Pump Seals",              6,  "units",     2,   0.02),
                ("bharati.food.frozen",      "bharati", "FOOD",       "Frozen Food Stock",               4800, "kg",      700,  19.2),
                ("bharati.medical.first_aid","bharati", "MEDICAL",    "First Aid Kits",                    32, "units",    10,   0.1),
            ]

            for it in inventory_seed:
                iid, sid, cat, nm, qty, un, mth, br = it
                days_rem = int(qty / br) if br > 0 else 9999
                await db.execute(text("""
                    INSERT INTO inventory_items
                        (item_id, station_id, category, name, quantity, unit,
                         min_safety_threshold, daily_burn_rate, days_remaining,
                         last_updated, updated_by, synced_to_cloud)
                    VALUES (:id, :sid, :cat, :nm, :qty, :un, :mth, :br, :dr, :lu, 'system', true)
                    ON CONFLICT (item_id) DO NOTHING
                """), {
                    "id": iid, "sid": sid, "cat": cat, "nm": nm,
                    "qty": qty, "un": un, "mth": mth, "br": br,
                    "dr": days_rem, "lu": _now(),
                })
            await db.commit()
            ok(f"Inventory: {len(inventory_seed)} items seeded")

        # ── LINK STATUS LOG ─────────────────────────────────────────────────
        existing_links = (await db.execute(text("SELECT COUNT(*) FROM link_status_log"))).scalar() or 0
        if existing_links < 10:
            link_rows = []
            for i in range(48):  # last 4 hours at 5-min intervals
                ts = _ago(minutes=i * 5)
                link_rows.append({"sid": "maitri",  "ls": "UP",       "lat": jitter(245.0, 0.05), "ploss": jitter(1.2, 0.2),  "qd": 245760, "ts": ts})
                link_rows.append({"sid": "bharati", "ls": "DEGRADED" if i < 12 else "UP", "lat": jitter(892.0, 0.08), "ploss": jitter(4.8, 0.3),  "qd": 819200, "ts": ts})

            for lr in link_rows:
                await db.execute(text("""
                    INSERT INTO link_status_log
                        (station_id, link_state, latency_ms, packet_loss_pct,
                         queue_depth_bytes, recorded_at)
                    VALUES (:sid, :ls, :lat, :ploss, :qd, :ts)
                """), lr)
            await db.commit()
            ok(f"Link status log: {len(link_rows)} rows")

        # ── AI PREDICTIONS ──────────────────────────────────────────────────
        existing_preds = (await db.execute(text("SELECT COUNT(*) FROM ai_predictions"))).scalar() or 0
        if existing_preds < 4:
            predictions = [
                ("maitri",  "fuel_depletion_prophet_v2", "fuel_pct",       258, 35.2, 30.1, 40.3, "WARNING",  _ago(days=-90),  1.0),
                ("maitri",  "fuel_depletion_prophet_v2", "days_to_minimum",258, None, None, None,   "WARNING",  _ago(days=-90),  None),
                ("bharati", "fuel_depletion_prophet_v2", "fuel_pct",       127, 22.4, 17.8, 27.0, "CRITICAL", _ago(days=-60),  1.0),
                ("bharati", "fuel_depletion_prophet_v2", "days_to_minimum",127, None, None, None,  "CRITICAL", _ago(days=-60),  None),
                ("maitri",  "vibration_anomaly_v1",      "vibration_rms",    1, 0.04, 0.02, 0.07, "NOMINAL",  _ago(hours=-1),  0.92),
                ("bharati", "vibration_anomaly_v1",      "vibration_rms",    1, 0.09, 0.06, 0.13, "WARNING",  _ago(hours=-1),  0.87),
            ]
            for p in predictions:
                sid, mdl, tgt, days_fwd, pv, cl, cu, rl, pfd, conf = p
                await db.execute(text("""
                    INSERT INTO ai_predictions
                        (prediction_id, station_id, model_name, target_metric,
                         predicted_for_date, predicted_value, confidence_lower,
                         confidence_upper, risk_level, confidence, generated_at)
                    VALUES (:id, :sid, :mdl, :tgt, :pfd, :pv, :cl, :cu, :rl, :conf, :ga)
                """), {
                    "id": _uid(), "sid": sid, "mdl": mdl, "tgt": tgt,
                    "pfd": pfd, "pv": pv, "cl": cl, "cu": cu,
                    "rl": rl, "conf": conf, "ga": _now(),
                })
            await db.commit()
            ok(f"AI predictions: {len(predictions)} seeded")

        # ── RESUPPLY MANIFEST ───────────────────────────────────────────────
        existing_manifests = (await db.execute(text("SELECT COUNT(*) FROM resupply_manifests"))).scalar() or 0
        if existing_manifests < 1:
            mid = _uid()
            await db.execute(text("""
                INSERT INTO resupply_manifests
                    (manifest_id, station_id, expedition_name, voyage_year, ship_name,
                     departure_date, arrival_window_start, arrival_window_end, status,
                     notes, created_at, created_by)
                VALUES (:id, 'maitri', '44th Indian Antarctic Expedition', 2026,
                        'MV Vasiliy Golovnin', '2026-11-15', '2026-12-28', '2027-01-10',
                        'PLANNED', 'Annual resupply including 200,000L diesel, 12 months dry rations, medical supplies.',
                        :ca, 'logistics@ncpor.in')
            """), {"id": mid, "ca": _now()})
            line_items = [
                (mid, "maitri.fuel.diesel_main", "Diesel Fuel", 200000, "litres"),
                (mid, "maitri.food.dry_rations", "Dry Rations", 6000, "kg"),
                (mid, "maitri.medical.oxygen",   "Medical Oxygen Cylinders", 50, "units"),
                (mid, "maitri.parts.gen_filters","Generator Air Filters", 24, "units"),
            ]
            for m_id, item_id, item_name, qty, unit in line_items:
                await db.execute(text("""
                    INSERT INTO resupply_line_items
                        (line_item_id, manifest_id, item_id, item_name, quantity_delivered, unit)
                    VALUES (:lid, :mid, :iid, :inm, :qty, :un)
                """), {"lid": _uid(), "mid": m_id, "iid": item_id, "inm": item_name, "qty": qty, "un": unit})
            await db.commit()
            ok("Resupply manifest: 44th Expedition seeded")

    await engine.dispose()

    # ── SUMMARY ─────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"{G}{B}✓ VajraX Neon database fully initialised!{E}")
    print(f"\nYou can now start the backend:")
    print(f"  {C}PYTHONPATH=. uvicorn cloud.main:app --port 8200 --reload{E}")
    print(f"\nLogin with: admin / admin123")


if __name__ == "__main__":
    asyncio.run(main())
