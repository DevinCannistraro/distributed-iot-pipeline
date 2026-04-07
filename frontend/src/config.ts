/** Global threshold constants — easy to swap to per-freezer Firestore metadata later. */
export const TEMP_MIN_C = -25;
export const TEMP_MAX_C = -15;
export const STALE_THRESHOLD_MS = 90_000; // 90 seconds

/** URL of the Query Service analysis endpoint. Swap for Cloud Run URL in production. */
export const ANALYSIS_ENDPOINT = "http://localhost:8082/analysis";

/** Analysis is considered high-risk above this percentage. */
export const PCT_OVER_TEMP_THRESHOLD = 5;
