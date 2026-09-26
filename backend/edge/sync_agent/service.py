"""Edge Satellite Sync Agent — dequeues messages and forwards to Cloud via MQTT.

Lifecycle:
  1. start() — spawns the MQTT reconnect loop as a background task
  2. _on_mqtt_connected() — called every time MQTT connects
     a. Starts the flush loop (dequeue → envelope → publish)
     b. Starts the heartbeat loop (periodic link heartbeat)
  3. stop() — cancels all tasks gracefully

Link state tracking:
  - UP: last publish succeeded
  - DEGRADED: publish latency anomaly detected (future)
  - DOWN: MQTT disconnected or publish failed

On publish failure:
  - Item is requeued with backoff (not dropped)
  - link_state → DOWN
  - Next reconnect re-sends
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.crypto.signing import Signer
from shared.db.models.edge import LinkStatusRecord
from shared.utils.time import utcnow
from edge.sync_agent.envelope import build_envelope
from edge.sync_agent.mqtt_client import MQTTClient, QOS_CRITICAL, QOS_TELEMETRY
from edge.sync_agent.queue_manager import QueueManager

log = structlog.get_logger(__name__)

# Priority threshold for QoS 2 (exactly-once)
_QOS2_THRESHOLD = 1  # priority 0 and 1 → QoS 2


class SyncAgent:
    """Satellite sync agent: Edge outbound queue → MQTT → Cloud."""

    def __init__(
        self,
        station_id: str,
        mqtt_client: MQTTClient,
        queue_manager: QueueManager,
        session_factory: async_sessionmaker[AsyncSession],
        private_key_pem_path: str,
        heartbeat_interval_s: int = 60,
        flush_interval_s: float = 5.0,
        batch_size: int = 20,
    ) -> None:
        self._station_id = station_id
        self._mqtt = mqtt_client
        self._queue = queue_manager
        self._session_factory = session_factory
        self._private_key_pem_path = private_key_pem_path
        self._heartbeat_interval_s = heartbeat_interval_s
        self._flush_interval_s = flush_interval_s
        self._batch_size = batch_size
        self._signer: Optional[Signer] = None
        self._sequence: int = 0
        self._link_state: str = "DOWN"
        self._last_latency_ms: Optional[float] = None  # updated by heartbeat loop
        self._task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

    def _get_signer(self) -> Signer:
        if self._signer is None:
            self._signer = Signer.from_pem_file(self._private_key_pem_path)
        return self._signer

    async def start(self) -> None:
        """Start the MQTT reconnect loop in the background."""
        self._running = True
        self._task = asyncio.create_task(
            self._mqtt.run_with_reconnect(on_connected=self._on_mqtt_connected),
            name=f"sync-agent-{self._station_id}",
        )
        log.info("edge.sync_agent.started", station_id=self._station_id)

    async def stop(self) -> None:
        """Cancel all tasks and update link state to DOWN."""
        self._running = False
        for t in (self._task, self._heartbeat_task):
            if t and not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        await self._record_link_state("DOWN")
        log.info("edge.sync_agent.stopped", station_id=self._station_id)

    # ---------------------------------------------------------------------------
    # Internal loops
    # ---------------------------------------------------------------------------

    async def _on_mqtt_connected(self) -> None:
        """Called each time MQTT connects successfully."""
        await self._record_link_state("UP")
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name=f"heartbeat-{self._station_id}"
        )
        try:
            await self._flush_loop()
        finally:
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()

    async def _flush_loop(self) -> None:
        """Continuously dequeue and publish while connected.

        Network quality (network_pct) is estimated from heartbeat latency:
          - No latency data yet            → assume 100% (good)
          - latency <= 500ms               → good   (80-100%)
          - latency <= 1500ms              → medium (40-79%)
          - latency <= 4000ms              → slow   (10-39%)
          - latency >  4000ms or timeout   → critical (0-9%)

        network_pct is passed to dequeue_batch() so only eligible-priority
        items are dequeued and sent under constrained bandwidth.
        """
        while self._running:
            try:
                network_pct = self._estimate_network_pct()
                items = await self._queue.dequeue_batch(
                    self._batch_size,
                    network_pct=network_pct,
                )
                if items:
                    log.info(
                        "edge.sync_agent.flush_batch",
                        count=len(items),
                        network_pct=network_pct,
                        max_priority=self._queue.max_priority_for_bandwidth(network_pct),
                    )
                for item in items:
                    await self._publish_item(item)
            except Exception as exc:
                log.error("edge.sync_agent.flush_error", error=str(exc))
                await self._record_link_state("DEGRADED")
            await asyncio.sleep(self._flush_interval_s)

    def _estimate_network_pct(self) -> float:
        """Estimate network quality as a percentage from recent latency_ms.

        Thresholds:
          <= 500ms   → 90%  (good)
          <= 1500ms  → 60%  (medium)
          <= 4000ms  → 25%  (slow)
          >  4000ms  → 5%   (critical)
          No data    → 100% (assume good until proven otherwise)
        """
        if self._last_latency_ms is None:
            return 100.0
        ms = self._last_latency_ms
        if ms <= 500:
            return 90.0
        if ms <= 1500:
            return 60.0
        if ms <= 4000:
            return 25.0
        return 5.0

    async def _publish_item(self, item: Dict[str, Any]) -> None:
        """Wrap one queue item in a SyncEnvelope and publish over MQTT."""
        try:
            self._sequence += 1
            envelope = build_envelope(
                station_id=self._station_id,
                message_type=item["message_type"],
                payload=item["payload"],
                sequence_number=self._sequence,
                signer=self._get_signer(),
            )
            priority = item.get("priority", 3)
            qos = QOS_CRITICAL if priority <= _QOS2_THRESHOLD else QOS_TELEMETRY
            await self._mqtt.publish(item["message_type"], json.dumps(envelope), qos=qos)
            log.info(
                "edge.sync_agent.published",
                message_type=item["message_type"],
                seq=self._sequence,
                qos=qos,
            )
        except Exception as exc:
            log.error("edge.sync_agent.publish_failed", error=str(exc))
            await self._queue.requeue(item)
            await self._record_link_state("DOWN")
            raise

    async def _heartbeat_loop(self) -> None:
        """Publish link heartbeat and measure round-trip latency for bandwidth estimation."""
        while self._running:
            try:
                depth = await self._queue.queue_depth()
                network_pct = self._estimate_network_pct()
                hb = json.dumps({
                    "station_id": self._station_id,
                    "timestamp_utc": utcnow().isoformat(),
                    "link_state": self._link_state,
                    "queue_depth": depth,
                    "sequence": self._sequence,
                    "network_pct": network_pct,
                })
                # Measure publish latency as proxy for network quality
                t0 = asyncio.get_event_loop().time()
                await self._mqtt.publish_heartbeat(hb)
                latency_ms = (asyncio.get_event_loop().time() - t0) * 1000
                self._last_latency_ms = latency_ms

                log.debug(
                    "edge.sync_agent.heartbeat_sent",
                    queue_depth=depth,
                    latency_ms=round(latency_ms, 1),
                    network_pct=network_pct,
                )
            except Exception as exc:
                # On failure assume worst-case network
                self._last_latency_ms = 9999.0
                log.error("edge.sync_agent.heartbeat_error", error=str(exc))
            await asyncio.sleep(self._heartbeat_interval_s)

    async def _record_link_state(self, state: str) -> None:
        """Write a link state change to the DB if the state has changed."""
        if state == self._link_state:
            return
        self._link_state = state
        try:
            async with self._session_factory() as session:
                session.add(LinkStatusRecord(
                    station_id=self._station_id,
                    state=state,
                    timestamp_utc=utcnow(),
                ))
                await session.commit()
        except Exception as exc:
            log.error("edge.sync_agent.link_state_db_error", error=str(exc))

    # ---------------------------------------------------------------------------
    # Properties
    # ---------------------------------------------------------------------------

    @property
    def link_state(self) -> str:
        return self._link_state

    @property
    def sequence(self) -> int:
        return self._sequence
