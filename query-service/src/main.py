"""Query service: read-path analytics over BigQuery.

Exposes HTTP endpoints for the frontend to query historical freezer data.
Entirely separate from the processor (write/data plane) so each can scale
independently.
"""

import logging
import os

from flask import Flask, request, jsonify
from google.cloud import bigquery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_bq = None


def _get_bq() -> bigquery.Client | None:
    """Return a BigQuery client if BIGQUERY_DATASET_ID is configured, else None."""
    global _bq
    if _bq is None and os.environ.get("BIGQUERY_DATASET_ID"):
        _bq = bigquery.Client(project=os.environ.get("BIGQUERY_PROJECT_ID"))
    return _bq


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/analysis", methods=["GET"])
def analysis():
    """Return % of time each freezer in a store spent above TEMP_MAX_C over the last N hours.

    Query params:
      store_id (required)
      hours    (optional, default 4)

    Returns JSON: { "freezer-a": 12.5, "freezer-b": 0.0, ... }
    Returns {} if BigQuery is not configured or no data exists.
    """
    headers = {"Access-Control-Allow-Origin": "*"}

    store_id = request.args.get("store_id", "").strip()
    if not store_id:
        return jsonify({"error": "store_id is required"}), 400, headers

    hours = int(request.args.get("hours", 4))

    bq = _get_bq()
    if bq is None:
        return jsonify({}), 200, headers

    dataset_id = os.environ.get("BIGQUERY_DATASET_ID", "")
    project_id = os.environ.get("BIGQUERY_PROJECT_ID", "")
    temp_max = float(os.environ.get("TEMP_MAX_C", "-15"))

    query = f"""
        WITH intervals AS (
          SELECT
            freezer_id,
            temp_c,
            reading_time,
            LEAD(reading_time) OVER (PARTITION BY freezer_id ORDER BY reading_time) AS next_time
          FROM `{project_id}.{dataset_id}.sensor_readings`
          WHERE store_id = @store_id
            AND reading_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
        )
        SELECT
          freezer_id,
          ROUND(
            SAFE_DIVIDE(
              SUM(IF(temp_c > @temp_max,
                TIMESTAMP_DIFF(COALESCE(next_time, CURRENT_TIMESTAMP()), reading_time, SECOND), 0)),
              SUM(TIMESTAMP_DIFF(COALESCE(next_time, CURRENT_TIMESTAMP()), reading_time, SECOND))
            ) * 100, 1
          ) AS pct_over_temp
        FROM intervals
        GROUP BY freezer_id
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("store_id", "STRING", store_id),
            bigquery.ScalarQueryParameter("hours", "INT64", hours),
            bigquery.ScalarQueryParameter("temp_max", "FLOAT64", temp_max),
        ]
    )

    try:
        results = bq.query(query, job_config=job_config).result()
        data = {row.freezer_id: row.pct_over_temp for row in results}
        return jsonify(data), 200, headers
    except Exception:
        logger.exception("BigQuery analysis query failed for store=%s", store_id)
        return jsonify({}), 200, headers


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8082"))
    app.run(host="0.0.0.0", port=port)
