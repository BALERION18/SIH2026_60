"""Outbound queue manager — Redis sorted set for Edge→Cloud satellite queue.

Queue structure:
  Key:   queue:outbound:{station_id}          (Redis sorted set)
  Score: priority * 1_000_000_000_000 + created_at_unix_ms
  Value: JSON-serialised QueueItem dict

Lower score = dequeued first.
  Priority 0 — BLACK_BOX_FRAME, FAILED quality data  (life safety, never drop)
  Priority 1 — CRITICAL/HIGH alerts, environment domain (fire/CO)
  Priority 2 — MEDIUM/LOW alerts, energy domain, SUSPECT quality data
  Priority 3 — Normal telemetry (weather, logistics, inventory)
  Priority 4 — Seismic background, aggregates

Priority sources (in order of precedence):
  1. Explicit priority passed to enqueue()
  2. message_type → priority_map (from YAML config)
  3. domain → domain_priority (from YAML config)
  4. quality → quality_priority_bump (from YAML config)
  5. Fallback default: 3

Bandwidth-aware dequeue:
  Caller passes current network_pct (0-100).
  Only items with priority <= max_priority for that bandwidth tier are returned.

Overflow eviction: when queue exceeds max_bytes, highest-score (lowest priority)
items are removed first. Priority-0 items are NEVER evicted.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
import yaml

from edge.redis_client import get_redis, queue_key
from shared.utils.time import unix_ms, utcnow

log = structlog.get_logger(__name__)

# ── Fallback priority map (used if YAML not loaded) ──────────────────────────
_DEFAULT_MESSAGE_PRIORITY: Dict[str, int] = {
    "BLACK_BOX_FRAME":    0,
    "ALERT_CRITICAL":     1,
    "ALERT_HIGH":         1,
    "ALERT_MEDIUM":       2,
    "ALERT_LOW":          2,
    "ALERT_ACK":          2,
    "LINK_HEARTBEAT":     2,
    "INVENTORY_SNAPSHOT": 3,
    "SENSOR_BATCH":       3,
}

_DEFAULT_DOMAIN_PRIORITY: Dict[str, int] = {
    "environment": 1,
    "energy":      2,
    "weather":     3,
    "seismic":     4,
    "logistics":   3,
}

_DEFAULT_QUALITY_BUMP: Dict[str, int] = {
    "SUSPECT": 1,
    "FAILED":  0,
}

# bandwidth_pct → max priority level allowed to send
_DEFAULT_BANDWIDTH_TIERS: List[Dict[str, Any]] = [
    {"min_pct": 80, "max_priority": 4},   # good    — send everything
    {"min_pct": 40, "max_priority": 3},   # medium  — hold seismic/low
    {"min_pct": 10, "max_priority": 2},   # slow    — only alerts + energy
    {"min_pct":  0, "max_priority": 1},   # critical— only P0/P1
]


def _load_sync_config(station_id: str) -> Dict[str, Any]:
    """Load sync section from station YAML. Returns empty dict on failure."""
    try:
        cfg_path = (
            Path(__file__).resolve().parent.parent / "config" / f"{station_id}.yaml"
        )
        if cfg_path.exists():
            with open(cfg_path, "r") as f:
                return yaml.safe_load(f).get("sync", {})
    except Exception as exc:
        log.warning("edge.queue.config_load_error", error=str(exc))
    return {}


def _build_bandwidth_tiers(thresholds: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert YAML bandwidth_thresholds dict → sorted tier list."""
    tiers = []
    for _name, cfg in thresholds.items():
        tiers.append({"min_pct": cfg["min_pct"], "max_priority": cfg["max_priority"]})
    # Sort descending by min_pct so we match best tier first
    return sorted(tiers, key=lambda t: t["min_pct"], reverse=True)


def _score(priority: int, created_ms: int) -> float:
    """Sorted-set score: lower = dequeue first."""
    return float(priority * 1_000_000_000_000 + created_ms)


class QueueManager:
    """Manages the Redis outbound sorted-set queue for one station.

    Priority resolution order:
      explicit > message_type > domain > quality_bump > default(3)
    """

    def __init__(
        self,
        station_id: str,
        max_bytes: int = 512 * 1024 * 1024,  # 512 MB default
    ) -> None:
        self._station_id = station_id
        self._max_bytes = max_bytes
        self._key = queue_key(station_id)

        # Load config from YAML
        sync_cfg = _load_sync_config(station_id)

        self._message_priority: Dict[str, int] = {
            **_DEFAULT_MESSAGE_PRIORITY,
            **sync_cfg.get("priority_map", {}),
        }
        self._domain_priority: Dict[str, int] = {
            **_DEFAULT_DOMAIN_PRIORITY,
            **sync_cfg.get("domain_priority", {}),
        }
        self._quality_bump: Dict[str, int] = {
            **_DEFAULT_QUALITY_BUMP,
            **sync_cfg.get("quality_priority_bump", {}),
        }

        raw_bw = sync_cfg.get("bandwidth_thresholds", {})
        self._bandwidth_tiers: List[Dict[str, Any]] = (
            _build_bandwidth_tiers(raw_bw) if raw_bw else _DEFAULT_BANDWIDTH_TIERS
        )

        log.info(
            "edge.queue.config_loaded",
            station_id=station_id,
            message_types=len(self._message_priority),
            domains=len(self._domain_priority),
            bw_tiers=len(self._bandwidth_tiers),
        )

    # ── Priority resolution ───────────────────────────────────────────────────

    def resolve_priority(
        self,
        message_type: str,
        domain: Optional[str] = None,
        quality: Optional[str] = None,
        explicit: Optional[int] = None,
    ) -> int:
        """Resolve final queue priority from all available signals.

        Precedence:
          1. explicit override
          2. message_type lookup
          3. domain lookup (for SENSOR_BATCH — use domain priority)
          4. quality bump (SUSPECT → -1 tier, FAILED → priority 0)
        """
        # 1. Explicit override
        if explicit is not None:
            return explicit

        # 2. Message type lookup
        p = self._message_priority.get(message_type, 3)

        # 3. Domain refinement — only for SENSOR_BATCH
        if message_type == "SENSOR_BATCH" and domain:
            domain_p = self._domain_priority.get(domain.lower(), p)
            # Use domain priority directly — domain config is the authority
            p = domain_p

        # 4. Quality bump
        if quality and quality != "NOMINAL":
            bump = self._quality_bump.get(quality)
            if bump is not None:
                if quality == "FAILED":
                    p = 0   # FAILED data → highest priority, must investigate
                else:
                    p = max(0, p - bump)  # SUSPECT → bump up by configured amount

        return p

    def max_priority_for_bandwidth(self, network_pct: float) -> int:
        """Return max priority level allowed to send at given network quality.

        network_pct: 0-100 (100 = full bandwidth, 0 = no bandwidth).
        Items with priority > returned value are held back.
        """
        for tier in self._bandwidth_tiers:
            if network_pct >= tier["min_pct"]:
                return tier["max_priority"]
        return 1  # absolute fallback — only P0/P1

    # ── Queue operations ──────────────────────────────────────────────────────

    async def enqueue(
        self,
        message_type: str,
        payload: Dict[str, Any],
        priority: Optional[int] = None,
        source_id: Optional[str] = None,
        domain: Optional[str] = None,
        quality: Optional[str] = None,
    ) -> str:
        """Add one item to the outbound queue.

        Args:
            message_type: SENSOR_BATCH | ALERT_CRITICAL | BLACK_BOX_FRAME etc.
            payload:      The message body.
            priority:     Explicit override — skips resolution if set.
            source_id:    Optional sensor/alert ID for tracing.
            domain:       Sensor domain (energy/weather/environment/seismic).
            quality:      Sensor quality (NOMINAL/SUSPECT/FAILED).

        Returns:
            The generated item_id for tracking.
        """
        redis = get_redis()
        p = self.resolve_priority(message_type, domain=domain,
                                  quality=quality, explicit=priority)
        now_ms = unix_ms(utcnow())
        item_id = f"{message_type.lower()}-{now_ms}"

        item: Dict[str, Any] = {
            "item_id":      item_id,
            "station_id":   self._station_id,
            "message_type": message_type,
            "payload":      payload,
            "priority":     p,
            "domain":       domain,
            "quality":      quality,
            "created_ms":   now_ms,
            "source_id":    source_id,
            "attempts":     0,
        }
        value = json.dumps(item, default=str)
        score = _score(p, now_ms)
        await redis.zadd(self._key, {value: score})
        await self._maybe_evict()
        log.debug("edge.queue.enqueued", item_id=item_id, priority=p,
                  domain=domain, quality=quality)
        return item_id

    async def dequeue_batch(
        self,
        batch_size: int = 10,
        network_pct: float = 100.0,
    ) -> List[Dict[str, Any]]:
        """Atomically pop up to batch_size highest-priority items.

        Args:
            batch_size:  Max items to dequeue.
            network_pct: Current network quality 0-100.
                         Items with priority > max_priority for this tier
                         are left in the queue.
        """
        max_p = self.max_priority_for_bandwidth(network_pct)
        redis = get_redis()

        # Score upper bound: items with priority > max_p have score >= (max_p+1)*1e12
        max_score = float((max_p + 1) * 1_000_000_000_000 - 1)

        # Peek eligible items first, then pop only those
        raw = await redis.zrangebyscore(
            self._key, min=0, max=max_score, start=0, num=batch_size, withscores=False
        )
        if not raw:
            return []

        items: List[Dict[str, Any]] = []
        pipeline = redis.pipeline(transaction=True)
        for value in raw:
            pipeline.zrem(self._key, value)
        await pipeline.execute()

        for value in raw:
            try:
                decoded = value.decode() if isinstance(value, bytes) else value
                items.append(json.loads(decoded))
            except Exception as exc:
                log.error("edge.queue.decode_error", error=str(exc))

        if items:
            log.debug("edge.queue.dequeued", count=len(items),
                      network_pct=network_pct, max_priority=max_p)
        return items

    async def requeue(self, item: Dict[str, Any]) -> None:
        """Re-add a failed item with incremented attempt counter and backoff."""
        redis = get_redis()
        item["attempts"] = item.get("attempts", 0) + 1
        backoff_ms = min(item["attempts"] * 30_000, 300_000)
        score = _score(item["priority"], item["created_ms"] + backoff_ms)
        await redis.zadd(self._key, {json.dumps(item, default=str): score})

    async def queue_depth(self) -> int:
        """Number of items in queue."""
        return await get_redis().zcard(self._key)

    async def queue_size_bytes(self) -> int:
        """Approximate total queue size in bytes."""
        items = await get_redis().zrange(self._key, 0, -1)
        return sum(len(v) for v in items)

    # ── Eviction ─────────────────────────────────────────────────────────────

    async def _maybe_evict(self) -> None:
        """Evict lowest-priority items until queue is under max_bytes.

        Priority-0 items are NEVER evicted (life safety).
        Eviction starts from the highest score (lowest priority, oldest).
        """
        size = await self.queue_size_bytes()
        if size <= self._max_bytes:
            return

        redis = get_redis()
        evicted = 0

        while size > self._max_bytes:
            # Get the lowest priority (highest score) item
            candidates = await redis.zrevrange(self._key, 0, 0, withscores=True)
            if not candidates:
                break
            value, score = candidates[0]
            # Never evict priority-0 items
            priority = int(score // 1_000_000_000_000)
            if priority == 0:
                log.warning("edge.queue.eviction_blocked_p0",
                            station_id=self._station_id)
                break
            await redis.zrem(self._key, value)
            evicted += 1
            size = await self.queue_size_bytes()

        if evicted:
            log.warning("edge.queue.evicted",
                        station_id=self._station_id, count=evicted)
