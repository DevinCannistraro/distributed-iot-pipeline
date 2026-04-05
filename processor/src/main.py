"""Processor service: consumes Pub/Sub messages and writes to Firestore.

Supports two modes controlled by PROCESSOR_MODE env var:
  - "pull" (default, local dev): pulls from Pub/Sub subscription in a background thread
  - "push" (production): receives HTTP POST from Pub/Sub push subscription

Flask always runs for the /health endpoint regardless of mode.
"""

import base64
import json
import logging
import os
import threading
import time

from flask import Flask, request, jsonify
from google.cloud import firestore, pubsub_v1

from handler import process_reading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Lazy-init Firestore client (allows import without side effects for testing)
_db = None


def _get_db() -> firestore.Client:
    global _db
    if _db is None:
        project = os.environ.get("GCP_PROJECT_ID", "local-dev")
        _db = firestore.Client(project=project)
    return _db


# ---------- Push mode endpoint ----------

@app.route("/process", methods=["POST"])
def push_handler():
    """Receive a Pub/Sub push message and write to Firestore."""
    envelope = request.get_json(silent=True)
    if not envelope or "message" not in envelope:
        return "Bad request: missing Pub/Sub envelope", 400

    raw_data = base64.b64decode(envelope["message"]["data"])
    data = json.loads(raw_data)

    try:
        process_reading(data, _get_db())
    except ValueError as e:
        logger.warning("Invalid message payload: %s", e)
        # Return 204 so Pub/Sub doesn't retry a permanently bad message
        return "", 204
    except Exception:
        logger.exception("Failed to process reading")
        return "Internal error", 500

    return "", 204


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# ---------- Pull mode loop ----------

def _pull_loop(
    project_id: str,
    subscription_id: str,
    db: firestore.Client,
    stop_event: threading.Event,
):
    """Pull messages from Pub/Sub and process them. Runs in a background thread."""
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(project_id, subscription_id)

    logger.info("Pull loop started on %s", subscription_path)

    while not stop_event.is_set():
        try:
            response = subscriber.pull(
                request={"subscription": subscription_path, "max_messages": 10},
                timeout=10,
            )
        except Exception as e:
            # Timeout or transient error — retry
            logger.debug("Pull returned: %s", e)
            time.sleep(1)
            continue

        if not response.received_messages:
            continue

        ack_ids = []
        for msg in response.received_messages:
            try:
                data = json.loads(msg.message.data.decode("utf-8"))
                process_reading(data, db)
                ack_ids.append(msg.ack_id)
            except ValueError as e:
                logger.warning("Skipping invalid message: %s", e)
                ack_ids.append(msg.ack_id)  # ack to prevent redelivery
            except Exception:
                logger.exception("Failed to process message, will retry")
                # Don't ack — Pub/Sub will redeliver

        if ack_ids:
            subscriber.acknowledge(
                request={"subscription": subscription_path, "ack_ids": ack_ids}
            )

    logger.info("Pull loop stopped")


def main():
    mode = os.environ.get("PROCESSOR_MODE", "pull")
    project_id = os.environ.get("GCP_PROJECT_ID", "local-dev")
    subscription_id = os.environ.get("PUBSUB_SUBSCRIPTION_ID", "sensor-readings-pull")
    port = int(os.environ.get("PORT", "8081"))

    stop_event = threading.Event()

    if mode == "pull":
        db = _get_db()
        pull_thread = threading.Thread(
            target=_pull_loop,
            args=(project_id, subscription_id, db, stop_event),
            daemon=True,
        )
        pull_thread.start()
        logger.info("Processor started in PULL mode")
    else:
        logger.info("Processor started in PUSH mode")

    try:
        app.run(host="0.0.0.0", port=port)
    finally:
        stop_event.set()


if __name__ == "__main__":
    main()
