"""Edge ingestion service — validates, calibrates, and persists sensor batches.

Pipeline for each reading:
  1. Calibration   — apply offset + scale:  calibrated = (raw + offset) * scale
  2. Range check   — compare against nominal_min / nominal_max from sensor config
  3. Stuck check   — detect sensor frozen on same value (in-memory sliding window)
  4. Spike check   — detect sudden jump > max_rate_per_reading
  5. Quality tag   — assign NOMINAL / SUSPECT / FAILED
  6. Persist       — bulk insert into sensor_readings
  7. Publish       — Redis pub/sub for Alert Engine and Edge AI Engine

Quality rules:
  FAILED  → value outside nominal range  OR  calibrated value is NaN/Inf
  SUSPECT → sensor stuck  OR  spike/rate exceeded
  NOMINAL → all checks pass
"""
from __future__ import annotations

import json
import math
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models.edge import SensorReading
from edge.redis_client import get_redis, sensor_channel
from edge.sync_agent.queue_manager import QueueManager

log = structlog.get_logger(__name__)

# ── In-memory sliding window for stuck / rate detection ──────────────────────
# Maps sensor_id → deque of recent (calibrated) values
_sensor_history: Dict[str, Deque[float]] = {}
_MAX_WINDOW = 50  # keep at most 50 readings per sensor in memory


def _get_history(sensor_id: str, window: int) -> Deque[float]:
    """Return (or create) the sliding-window deque for a sensor."""
    if sensor_id not in _sensor_history:
        _sensor_history[sensor_id] = deque(maxlen=max(window, _MAX_WINDOW))
    return _sensor_history[sensor_id]


# ── Sensor config cache (loaded from maitri.yaml / bharati.yaml via edge config) ─
# Maps sensor_id → sensor config dict.  Populated lazily on first ingest call.
_sensor_cfg_cache: Dict[str, Dict[str, Any]] = {}


def _load_sensor_configs(station_id: str) -> Dict[str, Dict[str, Any]]:
    """Load sensor configs from the station YAML and cache them."""
    global _sensor_cfg_cache
    if _sensor_cfg_cache:
        return _sensor_cfg_cache

    try:
        import yaml
        from pathlib import Path
        cfg_path = Path(__file__).resolve().parent.parent / "config" / f"{station_id}.yaml"
        if cfg_path.exists():
            with open(cfg_path, "r") as f:
                station_cfg = yaml.safe_load(f)
            for sensor in station_cfg.get("sensors", []):
                _sensor_cfg_cache[sensor["sensor_id"]] = sensor
            log.info("edge.ingestion.sensor_config_loaded",
                     station_id=station_id, count=len(_sensor_cfg_cache))
        else:
            log.warning("edge.ingestion.sensor_config_missing", path=str(cfg_path))
    except Exception as exc:
        log.error("edge.ingestion.sensor_config_load_error", error=str(exc))

    return _sensor_cfg_cache


# ── Validation / calibration logic ───────────────────────────────────────────

def _calibrate(raw: float, cfg: Optional[Dict[str, Any]]) -> float:
    """Apply offset + scale calibration.  Returns calibrated value."""
    if cfg is None:
        return raw
    cal = cfg.get("calibration", {})
    offset = float(cal.get("offset", 0.0))
    scale = float(cal.get("scale", 1.0))
    return (raw + offset) * scale


def _determine_quality(
    sensor_id: str,
    calibrated: float,
    cfg: Optional[Dict[str, Any]],
) -> str:
    """
    Run all validation checks and return quality string.

    Checks (in order of severity):
      1. NaN / Inf                → FAILED
      2. Nominal range violation  → FAILED
      3. Stuck sensor             → SUSPECT
      4. Spike / rate of change   → SUSPECT
    """
    # 1. Sanity check
    if not math.isfinite(calibrated):
        log.warning("edge.validation.non_finite", sensor_id=sensor_id, value=calibrated)
        return "FAILED"

    if cfg is None:
        return "NOMINAL"

    cal = cfg.get("calibration", {})
    nominal_min: Optional[float] = cfg.get("nominal_min")
    nominal_max: Optional[float] = cfg.get("nominal_max")

    # 2. Range check
    if nominal_min is not None and calibrated < nominal_min:
        log.warning("edge.validation.range_low",
                    sensor_id=sensor_id, value=calibrated, min=nominal_min)
        return "FAILED"
    if nominal_max is not None and calibrated > nominal_max:
        log.warning("edge.validation.range_high",
                    sensor_id=sensor_id, value=calibrated, max=nominal_max)
        return "FAILED"

    stuck_threshold = float(cal.get("stuck_threshold", 0.0))
    stuck_window = int(cal.get("stuck_window_readings", 0))
    max_rate = cal.get("max_rate_per_reading")

    history = _get_history(sensor_id, max(stuck_window, 2))

    # 3. Stuck detection (only if threshold and window are configured)
    if stuck_window > 1 and stuck_threshold > 0.0 and len(history) >= stuck_window:
        window_vals = list(history)[-stuck_window:]
        spread = max(window_vals) - min(window_vals)
        if spread <= stuck_threshold:
            log.warning("edge.validation.stuck",
                        sensor_id=sensor_id, spread=spread,
                        window=stuck_window, threshold=stuck_threshold)
            return "SUSPECT"

    # 4. Spike / rate-of-change check
    if max_rate is not None and len(history) > 0:
        last_val = history[-1]
        rate = abs(calibrated - last_val)
        if rate > float(max_rate):
            log.warning("edge.validation.spike",
                        sensor_id=sensor_id, rate=rate, max_rate=max_rate,
                        prev=last_val, current=calibrated)
            return "SUSPECT"

    return "NOMINAL"


# ── Main service ──────────────────────────────────────────────────────────────

class IngestionService:
    """Handles a single SensorBatch: validates, calibrates, persists, publishes."""

    def __init__(
        self,
        session: AsyncSession,
        station_id: str,
        queue_manager: Optional[QueueManager] = None,
    ) -> None:
        self._session = session
        self._station_id = station_id
        self._sensor_cfgs = _load_sensor_configs(station_id)
        self._queue = queue_manager  # optional — only used when sync agent is running

    async def ingest(self, batch: Dict[str, Any]) -> int:
        """Validate, calibrate, persist and publish all readings in a batch.

        Args:
            batch: SensorBatch-compatible dict from the simulator or hardware driver.

        Returns:
            Number of readings successfully ingested.

        Raises:
            ValueError: If batch station_id doesn't match this Edge's station_id.
        """
        batch_station = batch.get("station_id", "")
        if batch_station != self._station_id:
            raise ValueError(
                f"Batch station_id {batch_station!r} does not match "
                f"this Edge station {self._station_id!r}"
            )

        readings: List[Dict[str, Any]] = batch.get("readings", [])
        if not readings:
            return 0

        # Process each reading: calibrate → validate → tag quality
        processed: List[Dict[str, Any]] = []
        quality_counts: Dict[str, int] = {"NOMINAL": 0, "SUSPECT": 0, "FAILED": 0}

        for r in readings:
            sensor_id = r.get("sensor_id", "")
            raw_value = float(r.get("value", 0.0))
            cfg = self._sensor_cfgs.get(sensor_id)

            # Step 1 — calibrate
            calibrated = _calibrate(raw_value, cfg)

            # Step 2-4 — validate and assign quality
            quality = _determine_quality(sensor_id, calibrated, cfg)
            quality_counts[quality] = quality_counts.get(quality, 0) + 1

            # Update sliding window AFTER quality check (so spike uses previous value)
            history = _get_history(sensor_id, int(
                (cfg or {}).get("calibration", {}).get("stuck_window_readings", 2)
            ))
            history.append(calibrated)

            # Build processed reading (use calibrated value, attach quality)
            processed.append({**r, "value": calibrated, "quality": quality})

        # Bulk insert
        rows = [_reading_to_row(r) for r in processed]
        await self._session.execute(
            SensorReading.__table__.insert(),
            rows,
        )

        # Enqueue to outbound sync queue with quality-aware priority
        if self._queue is not None:
            await self._enqueue_batch(processed)

        # Publish to Redis pub/sub
        await self._publish_readings(processed)

        log.info(
            "edge.ingestion.batch_ingested",
            station_id=self._station_id,
            count=len(processed),
            batch_id=batch.get("batch_id", ""),
            quality_nominal=quality_counts["NOMINAL"],
            quality_suspect=quality_counts["SUSPECT"],
            quality_failed=quality_counts["FAILED"],
        )
        return len(processed)

    async def _enqueue_batch(self, readings: List[Dict[str, Any]]) -> None:
        """Enqueue sensor batch to the outbound sync queue.

        Quality-based priority logic:
          - All NOMINAL readings → one SENSOR_BATCH per domain (priority from domain)
          - Any SUSPECT readings → same batch but priority bumped by QueueManager
          - Any FAILED readings  → separate SENSOR_BATCH at priority 0 (must investigate)

        Groups readings by domain so domain priority is correctly applied.
        FAILED readings are separated from NOMINAL/SUSPECT for immediate attention.
        """
        # Separate FAILED from rest
        failed: List[Dict[str, Any]] = []
        normal: List[Dict[str, Any]] = []
        for r in readings:
            if r.get("quality") == "FAILED":
                failed.append(r)
            else:
                normal.append(r)

        # Group normal readings by domain
        by_domain: Dict[str, List[Dict[str, Any]]] = {}
        for r in normal:
            domain = r.get("domain", "unknown")
            by_domain.setdefault(domain, []).append(r)

        # Enqueue one batch per domain — QueueManager resolves domain+quality priority
        for domain, domain_readings in by_domain.items():
            # Determine worst quality in this domain batch
            qualities = {r.get("quality", "NOMINAL") for r in domain_readings}
            quality = "SUSPECT" if "SUSPECT" in qualities else "NOMINAL"

            await self._queue.enqueue(
                message_type="SENSOR_BATCH",
                payload={
                    "station_id": self._station_id,
                    "domain": domain,
                    "readings": domain_readings,
                },
                domain=domain,
                quality=quality,
            )
            log.debug("edge.ingestion.enqueued_batch",
                      domain=domain, count=len(domain_readings), quality=quality)

        # Enqueue FAILED readings separately at highest priority
        if failed:
            by_domain_failed: Dict[str, List[Dict[str, Any]]] = {}
            for r in failed:
                domain = r.get("domain", "unknown")
                by_domain_failed.setdefault(domain, []).append(r)

            for domain, failed_readings in by_domain_failed.items():
                await self._queue.enqueue(
                    message_type="SENSOR_BATCH",
                    payload={
                        "station_id": self._station_id,
                        "domain": domain,
                        "readings": failed_readings,
                        "contains_failed": True,
                    },
                    domain=domain,
                    quality="FAILED",
                )
                log.warning("edge.ingestion.enqueued_failed",
                            domain=domain, count=len(failed_readings))

    async def _publish_readings(self, readings: List[Dict[str, Any]]) -> None:
        """Publish all readings in a single Redis pipeline batch.

        Instead of one redis.publish() call per reading, we group all
        publish commands into one pipeline and execute them in a single
        round-trip to Redis.
        """
        redis = get_redis()

        # Group by domain so each channel gets one JSON array per domain
        by_domain: Dict[str, List[Dict[str, Any]]] = {}
        for r in readings:
            domain = r.get("domain", "unknown")
            by_domain.setdefault(domain, []).append(r)

        # Single pipeline — all publish commands sent in one batch
        async with redis.pipeline(transaction=False) as pipe:
            for domain, domain_readings in by_domain.items():
                channel = sensor_channel(self._station_id, domain)
                for reading in domain_readings:
                    pipe.publish(channel, json.dumps(reading, default=str))
            await pipe.execute()


# ── Row conversion ────────────────────────────────────────────────────────────

def _reading_to_row(r: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a processed SensorReading dict to a SQLAlchemy insert row dict."""
    ts_raw = r.get("timestamp_utc")
    if isinstance(ts_raw, str):
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    elif isinstance(ts_raw, datetime):
        ts = ts_raw
    else:
        ts = datetime.now(tz=timezone.utc)

    return {
        "station_id": r["station_id"],
        "sensor_id":  r["sensor_id"],
        "domain":     r.get("domain", ""),
        "metric_name": r.get("metric_name", ""),
        "value":      float(r["value"]),
        "unit":       r.get("unit", ""),
        "quality":    r.get("quality", "NOMINAL"),
        "asset_id":   r.get("asset_id") or None,
        "timestamp_utc": ts,
        "is_aggregate": r.get("is_aggregate", False),
        "aggregation_window_s": r.get("aggregation_window_s") or None,
    }
