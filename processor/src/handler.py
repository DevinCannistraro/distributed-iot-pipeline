"""Processor core logic: write sensor readings to Firestore with newer-wins idempotency."""

import logging
import os
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


def _stream_to_bigquery(reading: dict, bq_client, dataset_id: str, project_id: str) -> None:
    """Stream one reading row to BigQuery. Errors are logged but never propagate —
    a BigQuery failure must not block the Firestore hot path or cause Pub/Sub retries."""
    try:
        table_ref = f"{project_id}.{dataset_id}.sensor_readings"
        insert_id = f"{reading['store_id']}_{reading['freezer_id']}_{reading['reading_time'].isoformat()}"
        row = {
            "store_id": reading["store_id"],
            "freezer_id": reading["freezer_id"],
            "device_id": reading["device_id"],
            "temp_c": reading["temp_c"],
            "reading_time": reading["reading_time"].isoformat(),
            "received_at": reading["received_at"].isoformat(),
        }
        errors = bq_client.insert_rows_json(table_ref, [row], row_ids=[insert_id])
        if errors:
            logger.warning("BigQuery insert errors for %s/%s: %s", reading["store_id"], reading["freezer_id"], errors)
        else:
            logger.debug("BigQuery row written for %s/%s", reading["store_id"], reading["freezer_id"])
    except Exception:
        logger.exception("BigQuery write failed for %s/%s — skipping", reading["store_id"], reading["freezer_id"])


def process_reading(data: dict, db: firestore.Client, bq_client=None) -> bool:
    """Write a single sensor reading to Firestore using newer-wins idempotency.

    Document path: stores/{store_id}/freezers/{freezer_id}

    Uses a Firestore transaction to atomically check the existing reading_time
    and only write if the incoming reading is strictly newer. This prevents
    out-of-order Pub/Sub delivery from overwriting fresher data.

    If bq_client is provided, also streams the reading to BigQuery (cold path).
    BigQuery write failures are logged and swallowed — they never affect the hot path.

    Returns True if the Firestore document was written/updated, False if skipped.
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

    # Cold path: BigQuery write (always attempt, regardless of Firestore newer-wins result,
    # so the full history is preserved even for duplicate deliveries).
    if bq_client is not None:
        dataset_id = os.environ.get("BIGQUERY_DATASET_ID", "")
        project_id = os.environ.get("BIGQUERY_PROJECT_ID", "")
        if dataset_id and project_id:
            _stream_to_bigquery(reading, bq_client, dataset_id, project_id)

    return written
