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


class VirtualPi:
    """Simulates a single Pi reporting freezer temps over gRPC."""

    def __init__(
        self,
        device_id: str,
        store_id: str,
        freezers: list[str],
        target: str,
        interval: float,
    ):
        self.device_id = device_id
        self.store_id = store_id
        self.freezers = freezers
        self.target = target
        self.interval = interval
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
        channel = grpc.insecure_channel(self.target)
        stub = freezer_pb2_grpc.FreezerIngestionStub(channel)
        logger.info(
            "[%s] Started — store=%s freezers=%s interval=%ss target=%s",
            self.device_id,
            self.store_id,
            self.freezers,
            self.interval,
            self.target,
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
        help="gRPC target (host:port)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("REPORT_INTERVAL", "30")),
        help="Seconds between reports (default: 30)",
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
