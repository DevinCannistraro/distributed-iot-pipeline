"""gRPC ingestion server for the FreezerIngestion service."""

import asyncio
import logging
import os
from datetime import datetime, timezone

import grpc

from generated import freezer_pb2, freezer_pb2_grpc
from publisher import LogPublisher, Publisher, PubSubPublisher

logger = logging.getLogger(__name__)

TEMP_MIN = -50.0
TEMP_MAX = 60.0
# Allow reading_time to be up to this many seconds in the future (clock skew tolerance)
MAX_FUTURE_SECONDS = 300


class FreezerIngestionServicer(freezer_pb2_grpc.FreezerIngestionServicer):
    def __init__(self, publisher: Publisher) -> None:
        self._publisher = publisher

    async def ReportReadings(
        self,
        request: freezer_pb2.ReadingBatch,
        context: grpc.aio.ServicerContext,
    ) -> freezer_pb2.Ack:
        now = datetime.now(timezone.utc)

        if not request.store_id:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "store_id is required"
            )

        if not request.device_id:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "device_id is required"
            )

        if len(request.readings) == 0:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "readings must not be empty"
            )

        for reading in request.readings:
            error = _validate_reading(reading, now)
            if error:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, error)

        for reading in request.readings:
            await self._publisher.publish(
                store_id=request.store_id,
                freezer_id=reading.freezer_id,
                device_id=request.device_id,
                temp_c=reading.temp_c,
                reading_time=reading.reading_time,
                received_at=now,
            )

        logger.info(
            "Accepted %d readings from device=%s store=%s",
            len(request.readings),
            request.device_id,
            request.store_id,
        )
        return freezer_pb2.Ack(accepted=True)


def _validate_reading(
    reading: freezer_pb2.FreezerReading, now: datetime
) -> str | None:
    """Return an error string if the reading is invalid, else None."""
    if not reading.freezer_id:
        return "freezer_id is required"

    if not (TEMP_MIN <= reading.temp_c <= TEMP_MAX):
        return f"temp_c={reading.temp_c} out of range [{TEMP_MIN}, {TEMP_MAX}]"

    if not reading.reading_time.seconds and not reading.reading_time.nanos:
        return "reading_time is required"

    reading_dt = reading.reading_time.ToDatetime().replace(tzinfo=timezone.utc)
    if (reading_dt - now).total_seconds() > MAX_FUTURE_SECONDS:
        return f"reading_time is too far in the future: {reading_dt.isoformat()}"

    return None


def _create_publisher() -> Publisher:
    """Create the appropriate publisher based on environment."""
    project_id = os.environ.get("GCP_PROJECT_ID")
    topic_id = os.environ.get("PUBSUB_TOPIC_ID", "sensor-readings")

    if project_id:
        logger.info("Using PubSubPublisher (project=%s, topic=%s)", project_id, topic_id)
        return PubSubPublisher(project_id, topic_id)

    logger.info("No GCP_PROJECT_ID set — using LogPublisher (stdout only)")
    return LogPublisher()


async def serve(port: int = 50051, publisher: Publisher | None = None) -> None:
    """Start the gRPC server."""
    if publisher is None:
        publisher = _create_publisher()

    server = grpc.aio.server()
    freezer_pb2_grpc.add_FreezerIngestionServicer_to_server(
        FreezerIngestionServicer(publisher), server
    )
    listen_addr = f"0.0.0.0:{port}"
    server.add_insecure_port(listen_addr)
    logger.info("Ingestion server starting on %s", listen_addr)
    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(serve())
