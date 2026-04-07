import { useEffect, useState } from "react";
import type { Freezer } from "../hooks/useFreezersByStore";
import { TEMP_MIN_C, TEMP_MAX_C, STALE_THRESHOLD_MS, PCT_OVER_TEMP_THRESHOLD } from "../config";

interface FreezerCardProps {
  freezer: Freezer;
  pctOverTemp: number | null;
}

function formatRelativeTime(date: Date, now: Date): string {
  const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  return `${diffHr}h ago`;
}

function AnalysisStat({ pct }: { pct: number | null }) {
  if (pct === null) {
    return <span className="analysis-stat analysis-stat--unknown">📊 4h over temp: —</span>;
  }
  const isHigh = pct > PCT_OVER_TEMP_THRESHOLD;
  return (
    <span className={`analysis-stat ${isHigh ? "analysis-stat--high" : "analysis-stat--ok"}`}>
      📊 4h over temp: {pct.toFixed(1)}%
    </span>
  );
}

export function FreezerCard({ freezer, pctOverTemp }: FreezerCardProps) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  const tempOutOfRange =
    freezer.temp_c < TEMP_MIN_C || freezer.temp_c > TEMP_MAX_C;
  const isStale =
    now.getTime() - freezer.reading_time.getTime() > STALE_THRESHOLD_MS;

  let statusClass = "normal";
  if (tempOutOfRange && isStale) statusClass = "alert-both";
  else if (tempOutOfRange) statusClass = "alert-temp";
  else if (isStale) statusClass = "alert-stale";

  return (
    <div className={`freezer-card ${statusClass}`}>
      <div className="freezer-header">
        <h3>{freezer.freezer_id}</h3>
        <span className="device-id">{freezer.device_id}</span>
      </div>
      <div className="freezer-temp">{freezer.temp_c.toFixed(1)}°C</div>
      <div className="freezer-meta">
        <span className="reading-time">
          {formatRelativeTime(freezer.reading_time, now)}
        </span>
        {tempOutOfRange && (
          <span className="badge badge-temp">⚠ Out of range</span>
        )}
        {isStale && <span className="badge badge-stale">⚠ Stale</span>}
      </div>
      <div className="freezer-analysis">
        <AnalysisStat pct={pctOverTemp} />
      </div>
    </div>
  );
}
