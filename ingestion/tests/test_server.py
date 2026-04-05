"""Tests for the FreezerIngestion gRPC server."""

from datetime import datetime, timezone, timedelta

import grpc
import pytest
import pytest_asyncio

import sys
import os

# Support both PYTHONPATH (Docker) and local dev
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "generated"))

from generated import freezer_pb2, freezer_pb2_grpc
from google.protobuf.timestamp_pb2 import Timestamp
from publisher import LogPublisher
from server import FreezerIngestionServicer


def _make_timestamp(dt: datetime) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


def _now_ts() -> Timestamp:
    return _make_timestamp(datetime.now(timezone.utc))


def _make_batch(
    store_id: str = "store-101",
    device_id: str = "pi-test",
    readings: list | None = None,
) -> freezer_pb2.ReadingBatch:
    if readings is None:
        readings = [
            freezer_pb2.FreezerReading(
                freezer_id="freezer-a",
                temp_c=-18.5,
                reading_time=_now_ts(),
            )
        ]
    return freezer_pb2.ReadingBatch(
        store_id=store_id,
        device_id=device_id,
        readings=readings,
    )


@pytest_asyncio.fixture
async def grpc_channel():
    """Start an in-process gRPC server and yield a channel to it."""
    server = grpc.aio.server()
    publisher = LogPublisher()
    freezer_pb2_grpc.add_FreezerIngestionServicer_to_server(
        FreezerIngestionServicer(publisher), server
    )
    port = server.add_insecure_port("localhost:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"localhost:{port}")
    yield channel
    await channel.close()
    await server.stop(grace=0)


@pytest_asyncio.fixture
async def stub(grpc_channel):
    return freezer_pb2_grpc.FreezerIngestionStub(grpc_channel)


@pytest.mark.asyncio
async def test_valid_batch_accepted(stub):
    response = await stub.ReportReadings(_make_batch())
    assert response.accepted is True


@pytest.mark.asyncio
async def test_multiple_readings_accepted(stub):
    batch = _make_batch(
        readings=[
            freezer_pb2.FreezerReading(
                freezer_id="freezer-a", temp_c=-18.0, reading_time=_now_ts()
            ),
            freezer_pb2.FreezerReading(
                freezer_id="freezer-b", temp_c=-20.1, reading_time=_now_ts()
            ),
        ]
    )
    response = await stub.ReportReadings(batch)
    assert response.accepted is True


@pytest.mark.asyncio
async def test_empty_store_id_rejected(stub):
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await stub.ReportReadings(_make_batch(store_id=""))
    assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "store_id" in exc_info.value.details()


@pytest.mark.asyncio
async def test_empty_device_id_rejected(stub):
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await stub.ReportReadings(_make_batch(device_id=""))
    assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "device_id" in exc_info.value.details()


@pytest.mark.asyncio
async def test_empty_freezer_id_rejected(stub):
    batch = _make_batch(
        readings=[
            freezer_pb2.FreezerReading(
                freezer_id="", temp_c=-18.0, reading_time=_now_ts()
            )
        ]
    )
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await stub.ReportReadings(batch)
    assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "freezer_id" in exc_info.value.details()


@pytest.mark.asyncio
async def test_empty_readings_rejected(stub):
    batch = _make_batch(readings=[])
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await stub.ReportReadings(batch)
    assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "readings" in exc_info.value.details()


@pytest.mark.asyncio
async def test_temp_too_high_rejected(stub):
    batch = _make_batch(
        readings=[
            freezer_pb2.FreezerReading(
                freezer_id="freezer-a", temp_c=999.0, reading_time=_now_ts()
            )
        ]
    )
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await stub.ReportReadings(batch)
    assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "temp_c" in exc_info.value.details()


@pytest.mark.asyncio
async def test_temp_too_low_rejected(stub):
    batch = _make_batch(
        readings=[
            freezer_pb2.FreezerReading(
                freezer_id="freezer-a", temp_c=-100.0, reading_time=_now_ts()
            )
        ]
    )
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await stub.ReportReadings(batch)
    assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "temp_c" in exc_info.value.details()


@pytest.mark.asyncio
async def test_future_reading_time_rejected(stub):
    future_dt = datetime.now(timezone.utc) + timedelta(hours=1)
    batch = _make_batch(
        readings=[
            freezer_pb2.FreezerReading(
                freezer_id="freezer-a",
                temp_c=-18.0,
                reading_time=_make_timestamp(future_dt),
            )
        ]
    )
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await stub.ReportReadings(batch)
    assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "future" in exc_info.value.details()


@pytest.mark.asyncio
async def test_missing_reading_time_rejected(stub):
    batch = _make_batch(
        readings=[
            freezer_pb2.FreezerReading(
                freezer_id="freezer-a",
                temp_c=-18.0,
                # reading_time omitted — defaults to zero
            )
        ]
    )
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await stub.ReportReadings(batch)
    assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "reading_time" in exc_info.value.details()


@pytest.mark.asyncio
async def test_boundary_temp_accepted(stub):
    """Temperatures at the exact boundary should be accepted."""
    for temp in [-50.0, 60.0]:
        batch = _make_batch(
            readings=[
                freezer_pb2.FreezerReading(
                    freezer_id="freezer-a", temp_c=temp, reading_time=_now_ts()
                )
            ]
        )
        response = await stub.ReportReadings(batch)
        assert response.accepted is True
