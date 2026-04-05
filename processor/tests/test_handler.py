"""Tests for the processor handler — newer-wins Firestore idempotency logic.

These tests require a Firestore emulator running at FIRESTORE_EMULATOR_HOST.
"""

import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from google.cloud import firestore
from handler import process_reading, parse_reading


@pytest.fixture
def db():
    """Create a Firestore client pointing at the emulator."""
    project = os.environ.get("GCP_PROJECT_ID", "local-dev")
    return firestore.Client(project=project)


@pytest.fixture
def unique_ids():
    """Generate unique store/freezer IDs to isolate test runs."""
    suffix = uuid.uuid4().hex[:8]
    return {
        "store_id": f"test-store-{suffix}",
        "freezer_id": f"test-freezer-{suffix}",
    }


def _make_reading(store_id: str, freezer_id: str, temp_c: float, reading_time: datetime) -> dict:
    return {
        "store_id": store_id,
        "freezer_id": freezer_id,
        "device_id": "pi-test",
        "temp_c": temp_c,
        "reading_time": reading_time.isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


def _get_freezer_doc(db, store_id: str, freezer_id: str):
    return db.collection("stores").document(store_id).collection("freezers").document(freezer_id).get()


def _get_store_doc(db, store_id: str):
    return db.collection("stores").document(store_id).get()


def test_new_reading_is_written(db, unique_ids):
    """First reading for a freezer should be written to Firestore."""
    t1 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    data = _make_reading(unique_ids["store_id"], unique_ids["freezer_id"], -18.5, t1)

    result = process_reading(data, db)

    assert result is True
    doc = _get_freezer_doc(db, unique_ids["store_id"], unique_ids["freezer_id"])
    assert doc.exists
    assert doc.get("temp_c") == -18.5
    assert doc.get("freezer_id") == unique_ids["freezer_id"]

    # Store document should also be created
    store_doc = _get_store_doc(db, unique_ids["store_id"])
    assert store_doc.exists
    assert store_doc.get("store_id") == unique_ids["store_id"]


def test_newer_reading_overwrites(db, unique_ids):
    """A reading with a newer reading_time should overwrite the existing one."""
    t1 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 15, 12, 0, 30, tzinfo=timezone.utc)

    data1 = _make_reading(unique_ids["store_id"], unique_ids["freezer_id"], -18.5, t1)
    data2 = _make_reading(unique_ids["store_id"], unique_ids["freezer_id"], -19.2, t2)

    process_reading(data1, db)
    result = process_reading(data2, db)

    assert result is True
    doc = _get_freezer_doc(db, unique_ids["store_id"], unique_ids["freezer_id"])
    assert doc.get("temp_c") == -19.2


def test_older_reading_is_dropped(db, unique_ids):
    """A reading with an older reading_time should be ignored."""
    t1 = datetime(2026, 1, 15, 12, 0, 30, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)  # older

    data1 = _make_reading(unique_ids["store_id"], unique_ids["freezer_id"], -18.5, t1)
    data2 = _make_reading(unique_ids["store_id"], unique_ids["freezer_id"], -22.0, t2)

    process_reading(data1, db)
    result = process_reading(data2, db)

    assert result is False
    doc = _get_freezer_doc(db, unique_ids["store_id"], unique_ids["freezer_id"])
    assert doc.get("temp_c") == -18.5  # unchanged


def test_same_timestamp_is_idempotent(db, unique_ids):
    """A reading with the same reading_time should not overwrite."""
    t1 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    data1 = _make_reading(unique_ids["store_id"], unique_ids["freezer_id"], -18.5, t1)
    data2 = _make_reading(unique_ids["store_id"], unique_ids["freezer_id"], -22.0, t1)

    process_reading(data1, db)
    result = process_reading(data2, db)

    assert result is False
    doc = _get_freezer_doc(db, unique_ids["store_id"], unique_ids["freezer_id"])
    assert doc.get("temp_c") == -18.5  # first write wins for same timestamp


def test_malformed_payload_raises():
    """Missing required fields should raise ValueError."""
    with pytest.raises(ValueError, match="store_id"):
        parse_reading({"freezer_id": "f1", "device_id": "pi", "temp_c": -18.0,
                        "reading_time": "2026-01-01T00:00:00+00:00",
                        "received_at": "2026-01-01T00:00:00+00:00"})

    with pytest.raises(ValueError, match="freezer_id"):
        parse_reading({"store_id": "s1", "device_id": "pi", "temp_c": -18.0,
                        "reading_time": "2026-01-01T00:00:00+00:00",
                        "received_at": "2026-01-01T00:00:00+00:00"})

    with pytest.raises(ValueError, match="temp_c"):
        parse_reading({"store_id": "s1", "freezer_id": "f1", "device_id": "pi",
                        "reading_time": "2026-01-01T00:00:00+00:00",
                        "received_at": "2026-01-01T00:00:00+00:00"})
