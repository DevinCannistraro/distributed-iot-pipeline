"""Processor core logic: write sensor readings to Firestore with newer-wins idempotency."""

import logging
from datetime import datetime, timezone

from google.cloud import firestore

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("store_id", "freezer_id", "device_id", "temp_c", "reading_time", "received_at")


def parse_reading(data: dict) -> dict:
    """Validate and normalise a raw Pub/Sub message payload.

    Returns a dict ready for Firestore write.
    Raises ValueError on missing/malformed fields.
    """
    for field in REQUIRED_FIELDS:
        if field not in data or data[field] is None or data[field] == "":
            raise ValueError(f"Missing required field: {field}")

    reading_time = datetime.fromisoformat(data["reading_time"])
    received_at = datetime.fromisoformat(data["received_at"])

    return {
        "store_id": data["store_id"],
        "freezer_id": data["freezer_id"],
        "device_id": data["device_id"],
        "temp_c": float(data["temp_c"]),
        "reading_time": reading_time,
        "received_at": received_at,
    }


def process_reading(data: dict, db: firestore.Client) -> bool:
    """Write a single sensor reading to Firestore using newer-wins idempotency.

    Document path: stores/{store_id}/freezers/{freezer_id}

    Uses a Firestore transaction to atomically check the existing reading_time
    and only write if the incoming reading is strictly newer. This prevents
    out-of-order Pub/Sub delivery from overwriting fresher data.

    Returns True if the document was written/updated, False if skipped.
    """
    reading = parse_reading(data)
    store_id = reading["store_id"]
    freezer_id = reading["freezer_id"]

    store_ref = db.collection("stores").document(store_id)
    freezer_ref = store_ref.collection("freezers").document(freezer_id)

    @firestore.transactional
    def _update_in_transaction(txn, fref, sref, new_reading):
        snapshot = fref.get(transaction=txn)

        if snapshot.exists:
            existing_time = snapshot.get("reading_time")
            # Firestore stores datetime as DatetimeWithNanoseconds; compare directly
            if existing_time and new_reading["reading_time"] <= existing_time:
                logger.debug(
                    "Skipping older/duplicate reading for %s/%s (existing=%s, incoming=%s)",
                    store_id,
                    freezer_id,
                    existing_time.isoformat(),
                    new_reading["reading_time"].isoformat(),
                )
                return False

        # Upsert the store document (enables frontend store listing)
        txn.set(sref, {"store_id": store_id}, merge=True)

        # Write the freezer reading
        txn.set(fref, {
            "freezer_id": new_reading["freezer_id"],
            "device_id": new_reading["device_id"],
            "temp_c": new_reading["temp_c"],
            "reading_time": new_reading["reading_time"],
            "received_at": new_reading["received_at"],
        })
        return True

    txn = db.transaction()
    written = _update_in_transaction(txn, freezer_ref, store_ref, reading)

    if written:
        logger.info(
            "Wrote reading: %s/%s temp=%.2f",
            store_id,
            freezer_id,
            reading["temp_c"],
        )
    return written
