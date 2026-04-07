import { useEffect, useState, useRef } from "react";
import { ANALYSIS_ENDPOINT } from "../config";

/** Maps freezer_id → percentage of last N hours spent above max temp (0–100). */
export type AnalysisResult = Record<string, number | null>;

export function useAnalysis(storeId: string | null, hours = 4) {
  const [result, setResult] = useState<AnalysisResult>({});
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!storeId) {
      setResult({});
      return;
    }

    async function fetchAnalysis() {
      try {
        const url = `${ANALYSIS_ENDPOINT}?store_id=${encodeURIComponent(storeId!)}&hours=${hours}`;
        const res = await fetch(url);
        if (res.ok) {
          const data: Record<string, number> = await res.json();
          setResult(data);
        }
      } catch {
        // Network error or endpoint unavailable — keep previous result silently
      }
    }

    fetchAnalysis();
    intervalRef.current = setInterval(fetchAnalysis, 60_000);

    return () => {
      if (intervalRef.current !== null) clearInterval(intervalRef.current);
    };
  }, [storeId, hours]);

  return result;
}
