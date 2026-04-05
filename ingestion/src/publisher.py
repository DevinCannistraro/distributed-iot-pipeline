"""Publisher interface and implementations for forwarding readings to Pub/Sub."""

import abc
import json
import logging
from datetime import datetime, timezone

from google.cloud import pubsub_v1
from google.protobuf.timestamp_pb2 import Timestamp

logger = logging.getLogger(__name__)


class Publisher(abc.ABC):
    """Abstract publisher interface — allows stub/real swap for testing."""

    @abc.abstractmethod
    async def publish(
        self,
        store_id: str,
        freezer_id: str,
        device_id: str,
        temp_c: float,
        reading_time: Timestamp,
        received_at: datetime,
    ) -> None: ...


class LogPublisher(Publisher):
    """Stub that logs readings to stdout. Used in tests and local dev without Pub/Sub."""

    async def publish(
        self,
        store_id: str,
        freezer_id: str,
        device_id: str,
        temp_c: float,
        reading_time: Timestamp,
        received_at: datetime,
    ) -> None:
        logger.info(
            "PUBLISH store=%s freezer=%s device=%s temp=%.2f reading_time=%s received_at=%s",
            store_id,
            freezer_id,
            device_id,
            temp_c,
            _ts_to_iso(reading_time),
            received_at.isoformat(),
        )


class PubSubPublisher(Publisher):
    """Publishes individual readings to a Cloud Pub/Sub topic."""

    def __init__(self, project_id: str, topic_id: str) -> None:
        self._publisher = pubsub_v1.PublisherClient()
        self._topic_path = self._publisher.topic_path(project_id, topic_id)

    async def publish(
        self,
        store_id: str,
        freezer_id: str,
        device_id: str,
        temp_c: float,
        reading_time: Timestamp,
        received_at: datetime,
    ) -> None:
        payload = json.dumps(
            {
                "store_id": store_id,
                "freezer_id": freezer_id,
                "device_id": device_id,
                "temp_c": temp_c,
                "reading_time": _ts_to_iso(reading_time),
                "received_at": received_at.isoformat(),
            }
        ).encode("utf-8")

        future = self._publisher.publish(
            self._topic_path,
            data=payload,
            store_id=store_id,
            freezer_id=freezer_id,
        )
        future.result()  # block until confirmed
        logger.debug("Published reading for %s/%s", store_id, freezer_id)


def _ts_to_iso(ts: Timestamp) -> str:
    """Convert a protobuf Timestamp to ISO 8601 string."""
    dt = ts.ToDatetime().replace(tzinfo=timezone.utc)
    return dt.isoformat()
