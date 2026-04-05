"""Create the sensor-readings topic and subscription on the Pub/Sub emulator."""

import os

os.environ["PUBSUB_EMULATOR_HOST"] = "localhost:8085"

from google.cloud import pubsub_v1

project_id = "local-dev"
topic_id = "sensor-readings"
subscription_id = "sensor-readings-pull"

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(project_id, topic_id)

try:
    publisher.create_topic(request={"name": topic_path})
    print(f"Created topic: {topic_path}")
except Exception as e:
    print(f"Topic may already exist: {e}")

subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(project_id, subscription_id)

try:
    subscriber.create_subscription(
        request={"name": subscription_path, "topic": topic_path}
    )
    print(f"Created subscription: {subscription_path}")
except Exception as e:
    print(f"Subscription may already exist: {e}")
