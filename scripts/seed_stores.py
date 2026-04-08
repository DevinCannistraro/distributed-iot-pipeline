"""Seed store and freezer names into production Firestore.

Matches the store/freezer IDs in edge-simulator/config.yaml.
Run once after Phase 4 deployment to populate display names.

Usage:
    python scripts/seed_stores.py
"""

from google.cloud import firestore

STORES = {
    "store-101": {
        "name": "Store 101 - Boston",
        "freezers": {
            "freezer-a": "Walk-in Freezer A",
            "freezer-b": "Walk-in Freezer B",
            "freezer-c": "Prep Freezer C",
        },
    },
    "store-202": {
        "name": "Store 202 - Cambridge",
        "freezers": {
            "freezer-a": "Walk-in Freezer A",
            "freezer-b": "Display Case B",
            "freezer-c": "Ice Cream Case C",
        },
    },
}


def main():
    db = firestore.Client(project="distributed-iot-pipeline")

    for store_id, store_data in STORES.items():
        store_ref = db.collection("stores").document(store_id)
        store_ref.set({"store_id": store_id, "name": store_data["name"]}, merge=True)
        print(f"Seeded store: {store_id} — {store_data['name']}")

        for freezer_id, freezer_name in store_data["freezers"].items():
            freezer_ref = store_ref.collection("freezers").document(freezer_id)
            freezer_ref.set({"name": freezer_name}, merge=True)
            print(f"  Seeded freezer: {freezer_id} — {freezer_name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
