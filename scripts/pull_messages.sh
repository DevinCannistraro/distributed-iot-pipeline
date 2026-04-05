#!/usr/bin/env bash
# Pull and display messages from the Pub/Sub emulator for verification.
set -e

EMULATOR_HOST="${PUBSUB_EMULATOR_HOST:-localhost:8085}"
PROJECT_ID="local-dev"
SUBSCRIPTION_ID="sensor-readings-debug"

SUB_PATH="projects/${PROJECT_ID}/subscriptions/${SUBSCRIPTION_ID}"
PULL_URL="http://${EMULATOR_HOST}/v1/${SUB_PATH}:pull"

echo "Pulling messages from ${SUBSCRIPTION_ID}..."
RESPONSE=$(curl -s -X POST "${PULL_URL}" \
  -H "Content-Type: application/json" \
  -d '{"maxMessages": 20}')

# Check if we got any messages
if echo "${RESPONSE}" | grep -q "receivedMessages"; then
  echo "${RESPONSE}" | python3 -c "
import sys, json, base64
resp = json.load(sys.stdin)
ack_ids = []
for m in resp.get('receivedMessages', []):
    data = base64.b64decode(m['message']['data']).decode()
    attrs = m['message'].get('attributes', {})
    print(f'  data={json.dumps(json.loads(data), indent=2)}')
    print(f'  attributes={attrs}')
    print('  ---')
    ack_ids.append(m['ackId'])
print(f'\n{len(ack_ids)} messages received.')
" 2>/dev/null || echo "${RESPONSE}" | head -20
else
  echo "No messages available."
fi
