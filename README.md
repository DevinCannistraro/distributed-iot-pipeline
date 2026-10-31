# Freezer telemetry data plane

This document follows a freezer reading from the simulator through ingestion and Pub/Sub to its current-state and historical storage. It focuses on the data plane, not the dashboard.

## End-to-end view

```text
Virtual Pis
  └─ gRPC/TLS + ID token ──> Cloud Run ingestion
                                └─ Pub/Sub: sensor-readings
                                     └─ processor subscription
                                          (production wiring not checked in)
                                          ├─ Firestore: latest reading per freezer
                                          └─ BigQuery: sensor_readings history
```

The deployment-specific simulator target recorded in the repository is
`ingestion-884148543484.us-east1.run.app:443`. The deployment changes were
merged into the server's `main` in PR #5; this document uses the upstream
snapshot [`36ecea1`](https://github.com/DevinCannistraro/distributed-iot-pipeline/commit/36ecea1470c36ac5416e49805059752b212856d9)
as its source of truth. The deployment commit
[`9475b2e`](https://github.com/DevinCannistraro/distributed-iot-pipeline/commit/9475b2e600d0130e227bb06d51965257d8c88694)
says it was successfully deployed. That is evidence of a past deployment, not
confirmation that the services are still running.

## 1. Simulator creates and batches readings

[`edge-simulator/config.yaml`](edge-simulator/config.yaml) maps virtual Pis to
stores and freezer IDs. The checked-in sample has three Pis across two stores.
[the upstream simulator](https://github.com/DevinCannistraro/distributed-iot-pipeline/blob/36ecea1470c36ac5416e49805059752b212856d9/edge-simulator/src/run.py#L171)
starts one thread per Pi. Each freezer's temperature follows a random walk,
initialized near
-18°C and updated by up to 0.5°C per reporting interval
([temperature generation](https://github.com/DevinCannistraro/distributed-iot-pipeline/blob/36ecea1470c36ac5416e49805059752b212856d9/edge-simulator/src/run.py#L79)).

Each Pi sends **one batch per interval**, containing a reading for each freezer
assigned to it. A reading includes `freezer_id`, `temp_c`, and a UTC
`reading_time`; the batch adds `store_id` and `device_id`. The wire contract is
the protobuf service and messages in
[`proto/freezer/v1/freezer.proto`](proto/freezer/v1/freezer.proto#L8).
`device_id` is carried for tracing; `store_id` and `freezer_id` identify the
stored entities.

For the recorded deployment, `make run-simulator-cloud` targets that host on
port 443, supplies a service-account key, and sets a 30-second interval
([upstream Makefile](https://github.com/DevinCannistraro/distributed-iot-pipeline/blob/36ecea1470c36ac5416e49805059752b212856d9/Makefile#L77)).
The deployed simulator uses TLS and obtains an ID token with the Cloud Run host
as its audience
([upstream channel/auth code](https://github.com/DevinCannistraro/distributed-iot-pipeline/blob/36ecea1470c36ac5416e49805059752b212856d9/edge-simulator/src/run.py#L31)).
The ingestion server listens on the Cloud Run-provided `PORT` (defaulting to
50051) and binds its gRPC server to `0.0.0.0`
([upstream listener](https://github.com/DevinCannistraro/distributed-iot-pipeline/blob/36ecea1470c36ac5416e49805059752b212856d9/ingestion/src/server.py#L109)).
The Makefile records how to run the simulator against the service; it does not
provide a complete Cloud Run deployment command.

## 2. gRPC ingestion validates and publishes

The simulator calls the unary RPC
`/freezer.v1.FreezerIngestion/ReportReadings`. The server validates the batch
before publishing: store and device IDs must be present, it must contain
readings, freezer IDs and timestamps must be present, temperatures must be
between -50°C and 60°C, and a reading cannot be more than five minutes in the
future. See
[`ingestion/src/server.py` at upstream main](https://github.com/DevinCannistraro/distributed-iot-pipeline/blob/36ecea1470c36ac5416e49805059752b212856d9/ingestion/src/server.py#L21).

The server selects a publisher based on `GCP_PROJECT_ID`: with a project set it
uses Pub/Sub; without one it logs readings instead
([publisher selection](https://github.com/DevinCannistraro/distributed-iot-pipeline/blob/36ecea1470c36ac5416e49805059752b212856d9/ingestion/src/server.py#L91)). For each reading,
[`ingestion/src/publisher.py`](ingestion/src/publisher.py#L52) serializes a JSON
message containing `store_id`, `freezer_id`, `device_id`, `temp_c`,
`reading_time`, and `received_at`. It publishes each reading individually to
the `sensor-readings` topic, adding store and freezer IDs as Pub/Sub attributes.
It waits for Pub/Sub's publish future before the gRPC call returns its accepted
acknowledgement.

The topic's full resource name is
`projects/{GCP_PROJECT_ID}/topics/sensor-readings`. The Firebase project is
confirmed as `distributed-iot-pipeline` by
[`.firebaserc` at upstream main](https://github.com/DevinCannistraro/distributed-iot-pipeline/blob/36ecea1470c36ac5416e49805059752b212856d9/.firebaserc), and
the production Firestore seed script uses that same project
([`scripts/seed_stores.py`](https://github.com/DevinCannistraro/distributed-iot-pipeline/blob/36ecea1470c36ac5416e49805059752b212856d9/scripts/seed_stores.py#L32)). The Cloud Run
service's `GCP_PROJECT_ID` environment setting is not checked in, so the exact
production Pub/Sub resource path remains an inference.

## 3. Pub/Sub delivers to the processor

The processor supports two delivery modes in
[`processor/src/main.py`](processor/src/main.py#L3):

- **Pull:** it polls the configured subscription and acknowledges successfully
  processed messages. The local Compose configuration uses this mode and the
  subscription ID `sensor-readings-processor`.
- **Push:** Pub/Sub can POST its message envelope to the processor's `/process`
  endpoint. Payloads rejected by `process_reading` with `ValueError` receive a
  successful response so they are not retried; unexpected processing failures
  return an error so Pub/Sub can retry.

The repository does not record the production subscription's name or push
endpoint, nor which mode was actually configured in GCP. The local subscription
is created by [`scripts/create_topic.sh`](scripts/create_topic.sh#L1), and the
processor's pull/push behavior is in
[`processor/src/main.py`](processor/src/main.py#L55). The deployment PR adds
Cloud Run support to ingestion, but does not add processor deployment or
subscription-wiring configuration.

## 4. Processor validates and writes both storage paths

[`processor/src/handler.py`](processor/src/handler.py#L14) validates and parses
each JSON message, including converting its timestamps and temperature. It
then writes to Firestore and attempts the BigQuery write.

**Firestore — latest state.** The document path is
`stores/{store_id}/freezers/{freezer_id}`. A transaction compares the incoming
`reading_time` to the stored one and only replaces the freezer document when
the incoming reading is strictly newer. The transaction also upserts
`stores/{store_id}` so stores exist for downstream consumers
([transaction and document writes](processor/src/handler.py#L78)). Thus
out-of-order delivery cannot make the current freezer state older.

The deployment's [Firestore rules](https://github.com/DevinCannistraro/distributed-iot-pipeline/blob/36ecea1470c36ac5416e49805059752b212856d9/firestore.rules)
allow client reads and deny client writes. The processor and
[`scripts/seed_stores.py`](https://github.com/DevinCannistraro/distributed-iot-pipeline/blob/36ecea1470c36ac5416e49805059752b212856d9/scripts/seed_stores.py#L32) use server-side Google
Cloud clients, whose access is governed by IAM rather than these client
security rules. The seed script initializes store/freezer names in production
Firestore. One schema caveat: its freezer writes add a `name`, while the
processor's `txn.set` replaces the freezer document without merge; the first
sensor update therefore removes that seeded `name` field.

**BigQuery — history.** When `BIGQUERY_PROJECT_ID` and `BIGQUERY_DATASET_ID`
are configured, the processor streams each reading to
`{BIGQUERY_PROJECT_ID}.{BIGQUERY_DATASET_ID}.sensor_readings`. In the Compose
configuration that resolves to
`distributed-iot-pipeline.freezer_monitor.sensor_readings`. Rows include the
same identifiers and temperature plus measurement and ingestion timestamps.
An `insert_id` derived from store, freezer, and measurement time is supplied to
BigQuery. The BigQuery attempt is made even when Firestore skips an older or
duplicate reading, preserving the intended separation between current state
and history ([BigQuery write](processor/src/handler.py#L37)).

BigQuery is deliberately a best-effort side path: insert errors are logged and
swallowed so they do not prevent the Firestore write or cause Pub/Sub
redelivery. Consequently, a BigQuery failure is not retried by this message's
Pub/Sub delivery. Firestore or other uncaught processing failures, by contrast,
are left unacknowledged in pull mode or return an error in push mode.

## Local versus deployed addressing

The local Compose network uses:

| Hop | Local address or resource | Configuration/source |
|---|---|---|
| Simulator → ingestion | `ingestion:50051` | [`docker-compose.yaml`](docker-compose.yaml#L21) |
| Ingestion → Pub/Sub | `pubsub-emulator:8085`, project `local-dev`, topic `sensor-readings` | [`docker-compose.yaml`](docker-compose.yaml#L27) |
| Processor → Pub/Sub | Pull subscription `sensor-readings-processor` | [`docker-compose.yaml`](docker-compose.yaml#L71), [`scripts/create_topic.sh`](scripts/create_topic.sh#L23) |
| Processor → Firestore | `firestore-emulator:8080` | [`docker-compose.yaml`](docker-compose.yaml#L52) |

Compose emulates Pub/Sub and Firestore. Its processor also has BigQuery project
and dataset settings and mounts local Application Default Credentials; BigQuery
is not emulated there. The production simulator address, TLS/ID-token
authentication, and Cloud Run listener port are recorded in upstream `main`.
The production Pub/Sub subscription wiring and runtime environment variables
for ingestion and processor are still not checked into the repository.
