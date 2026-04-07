import { useFreezersByStore } from "../hooks/useFreezersByStore";
import { useAnalysis } from "../hooks/useAnalysis";
import { FreezerCard } from "./FreezerCard";

interface FreezerDashProps {
  storeId: string;
}

export function FreezerDash({ storeId }: FreezerDashProps) {
  const { freezers, loading } = useFreezersByStore(storeId);
  const analysis = useAnalysis(storeId);

  if (loading) {
    return (
      <div className="freezer-dash">
        <p className="loading">Loading freezers…</p>
      </div>
    );
  }

  if (freezers.length === 0) {
    return (
      <div className="freezer-dash">
        <p className="empty">No freezers reporting for this store</p>
      </div>
    );
  }

  return (
    <div className="freezer-dash">
      <div className="freezer-grid">
        {freezers.map((f) => (
          <FreezerCard key={f.id} freezer={f} pctOverTemp={analysis[f.freezer_id] ?? null} />
        ))}
      </div>
    </div>
  );
}
