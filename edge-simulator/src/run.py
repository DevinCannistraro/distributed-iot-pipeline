"""Edge simulator — spawns virtual Pis that send gRPC readings."""

import argparse
import logging
import os
import random
import signal
import sys
import threading
import time
from datetime import datetime, timezone

import grpc
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from generated import freezer_pb2, freezer_pb2_grpc
from google.protobuf.timestamp_pb2 import Timestamp

logger = logging.getLogger(__name__)

shutdown_event = threading.Event()


def _make_timestamp(dt: datetime) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


def _make_channel(target: str, sa_key_path: str | None) -> grpc.Channel:
    """Create a gRPC channel.

    If sa_key_path is provided, uses TLS + ID token auth for Cloud Run.
    Otherwise uses an insecure channel for local dev.
    """
    if sa_key_path:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import service_account

        audience = f"https://{target.split(':')[0]}"
        creds = service_account.IDTokenCredentials.from_service_account_file(
            sa_key_path, target_audience=audience
        )

        def _id_token_plugin(context, callback):
            creds.refresh(google_requests.Request())
            callback([("authorization", f"Bearer {creds.token}")], None)

        call_creds = grpc.metadata_call_credentials(_id_token_plugin)
        channel_creds = grpc.ssl_channel_credentials()
        combined_creds = grpc.composite_channel_credentials(channel_creds, call_creds)
        return grpc.secure_channel(target, combined_creds)

    return grpc.insecure_channel(target)


class VirtualPi:
    """Simulates a single Pi reporting freezer temps over gRPC."""

    def __init__(
        self,
        device_id: str,
        store_id: str,
        freezers: list[str],
        target: str,
        interval: float,
        sa_key_path: str | None = None,
    ):
        self.device_id = device_id
        self.store_id = store_id
        self.freezers = freezers
        self.target = target
        self.interval = interval
        self.sa_key_path = sa_key_path
        # Random-walk state: start each freezer at a typical temp
        self._temps = {fid: -18.0 + random.uniform(-2, 2) for fid in freezers}

    def _next_temp(self, freezer_id: str) -> float:
        """Random walk: drift +-0.5°C per tick."""
        current = self._temps[freezer_id]
        delta = random.uniform(-0.5, 0.5)
        new_temp = round(current + delta, 2)
        # Clamp to sane range
        new_temp = max(-45.0, min(55.0, new_temp))
        self._temps[freezer_id] = new_temp
        return new_temp

    def run(self) -> None:
        """Blocking loop — intended to be run in a thread."""
        channel = _make_channel(self.target, self.sa_key_path)
        stub = freezer_pb2_grpc.FreezerIngestionStub(channel)
        logger.info(
            "[%s] Started — store=%s freezers=%s interval=%ss target=%s auth=%s",
            self.device_id,
            self.store_id,
            self.freezers,
            self.interval,
            self.target,
            "id-token" if self.sa_key_path else "insecure",
        )

        while not shutdown_event.is_set():
            readings = []
            for fid in self.freezers:
                temp = self._next_temp(fid)
                readings.append(
                    freezer_pb2.FreezerReading(
                        freezer_id=fid,
                        temp_c=temp,
                        reading_time=_make_timestamp(datetime.now(timezone.utc)),
                    )
                )

            batch = freezer_pb2.ReadingBatch(
                store_id=self.store_id,
                device_id=self.device_id,
                readings=readings,
            )

            try:
                ack = stub.ReportReadings(batch, timeout=10)
                logger.info(
                    "[%s] Sent %d readings — accepted=%s",
                    self.device_id,
                    len(readings),
                    ack.accepted,
                )
            except grpc.RpcError as e:
                logger.error("[%s] gRPC error: %s", self.device_id, e)

            shutdown_event.wait(timeout=self.interval)

        channel.close()
        logger.info("[%s] Stopped", self.device_id)


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Edge simulator for freezer IoT")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "..", "config.yaml"),
        help="Path to Pi config YAML",
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("INGESTION_TARGET", "localhost:50051"),
        help="gRPC target (host:port). For Cloud Run: <host>:443",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("REPORT_INTERVAL", "30")),
        help="Seconds between reports (default: 30)",
    )
    parser.add_argument(
        "--sa-key",
        default=os.environ.get("SA_KEY_PATH"),
        help="Path to service account JSON key for Cloud Run auth (omit for local dev)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    threads: list[threading.Thread] = []

    for pi_cfg in config["pis"]:
        pi = VirtualPi(
            device_id=pi_cfg["device_id"],
            store_id=pi_cfg["store_id"],
            freezers=pi_cfg["freezers"],
            target=args.target,
            interval=args.interval,
            sa_key_path=args.sa_key,
        )
        t = threading.Thread(target=pi.run, name=pi.device_id, daemon=True)
        threads.append(t)
        t.start()

    def _shutdown(signum, frame):
        logger.info("Shutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("Edge simulator running with %d virtual Pis", len(threads))

    # Wait for shutdown
    while not shutdown_event.is_set():
        time.sleep(0.5)

    for t in threads:
        t.join(timeout=5)
    logger.info("All Pis stopped. Exiting.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
