import type { Store } from "../hooks/useStores";

interface StoreListProps {
  stores: Store[];
  loading: boolean;
  selectedStoreId: string | null;
  onSelectStore: (storeId: string) => void;
}

export function StoreList({
  stores,
  loading,
  selectedStoreId,
  onSelectStore,
}: StoreListProps) {
  if (loading) {
    return (
      <nav className="store-list">
        <p className="loading">Loading stores…</p>
      </nav>
    );
  }

  if (stores.length === 0) {
    return (
      <nav className="store-list">
        <p className="empty">No stores reporting</p>
      </nav>
    );
  }

  return (
    <nav className="store-list">
      <h2>Stores</h2>
      <ul>
        {stores.map((store) => (
          <li key={store.id}>
            <button
              className={`store-btn ${selectedStoreId === store.id ? "active" : ""}`}
              onClick={() => onSelectStore(store.id)}
            >
              {store.store_id}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
