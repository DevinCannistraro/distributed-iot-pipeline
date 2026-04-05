#!/usr/bin/env bash
# Create the sensor-readings topic and pull subscription on the Pub/Sub emulator.
set -e

EMULATOR_HOST="${PUBSUB_EMULATOR_HOST:-localhost:8085}"
PROJECT_ID="local-dev"
TOPIC_ID="sensor-readings"
SUBSCRIPTION_ID="sensor-readings-pull"

TOPIC_URL="http://${EMULATOR_HOST}/v1/projects/${PROJECT_ID}/topics/${TOPIC_ID}"
SUB_URL="http://${EMULATOR_HOST}/v1/projects/${PROJECT_ID}/subscriptions/${SUBSCRIPTION_ID}"

echo "Creating topic: ${TOPIC_ID}..."
curl -s -X PUT "${TOPIC_URL}" \
  -H "Content-Type: application/json" -d '{}' && echo ""

echo "Creating subscription: ${SUBSCRIPTION_ID}..."
curl -s -X PUT "${SUB_URL}" \
  -H "Content-Type: application/json" \
  -d "{\"topic\": \"projects/${PROJECT_ID}/topics/${TOPIC_ID}\"}" && echo ""

echo "Pub/Sub emulator setup complete."
