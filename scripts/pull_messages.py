"""Pull and display messages from the Pub/Sub emulator for verification."""

import json
import os

os.environ["PUBSUB_EMULATOR_HOST"] = "localhost:8085"

from google.cloud import pubsub_v1

project_id = "local-dev"
subscription_id = "sensor-readings-pull"

subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(project_id, subscription_id)

response = subscriber.pull(
    request={"subscription": subscription_path, "max_messages": 20},
    timeout=5,
)

if not response.received_messages:
    print("No messages available.")
else:
    ack_ids = []
    for msg in response.received_messages:
        data = json.loads(msg.message.data.decode("utf-8"))
        attrs = dict(msg.message.attributes)
        print(f"  data={json.dumps(data, indent=2)}")
        print(f"  attributes={attrs}")
        print("  ---")
        ack_ids.append(msg.ack_id)

    subscriber.acknowledge(
        request={"subscription": subscription_path, "ack_ids": ack_ids}
    )
    print(f"\nAcknowledged {len(ack_ids)} messages.")
