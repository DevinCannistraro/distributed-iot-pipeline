#!/usr/bin/env bash
# Create the sensor-readings topic and subscriptions on the Pub/Sub emulator.
set -e

EMULATOR_HOST="${PUBSUB_EMULATOR_HOST:-localhost:8085}"
PROJECT_ID="local-dev"
TOPIC_ID="sensor-readings"

TOPIC_URL="http://${EMULATOR_HOST}/v1/projects/${PROJECT_ID}/topics/${TOPIC_ID}"

# Wait for the emulator to be responsive
echo "Waiting for Pub/Sub emulator at ${EMULATOR_HOST}..."
until curl -sf "http://${EMULATOR_HOST}" > /dev/null 2>&1; do
  sleep 1
done
echo "Pub/Sub emulator is ready."

echo "Creating topic: ${TOPIC_ID}..."
curl -sf -X PUT "${TOPIC_URL}" \
  -H "Content-Type: application/json" -d '{}' && echo ""

# Processor subscription (primary consumer)
PROC_SUB_ID="sensor-readings-processor"
PROC_SUB_URL="http://${EMULATOR_HOST}/v1/projects/${PROJECT_ID}/subscriptions/${PROC_SUB_ID}"
echo "Creating subscription: ${PROC_SUB_ID}..."
curl -sf -X PUT "${PROC_SUB_URL}" \
  -H "Content-Type: application/json" \
  -d "{\"topic\": \"projects/${PROJECT_ID}/topics/${TOPIC_ID}\"}" && echo ""

# Debug/verification subscription (manual pull)
DEBUG_SUB_ID="sensor-readings-debug"
DEBUG_SUB_URL="http://${EMULATOR_HOST}/v1/projects/${PROJECT_ID}/subscriptions/${DEBUG_SUB_ID}"
echo "Creating subscription: ${DEBUG_SUB_ID}..."
curl -sf -X PUT "${DEBUG_SUB_URL}" \
  -H "Content-Type: application/json" \
  -d "{\"topic\": \"projects/${PROJECT_ID}/topics/${TOPIC_ID}\"}" && echo ""

# Write a marker file so the healthcheck knows setup is complete
touch /tmp/pubsub-ready

echo "Pub/Sub emulator setup complete."
