import { useState } from "react";
import { useStores } from "./hooks/useStores";
import { StoreList } from "./components/StoreList";
import { FreezerDash } from "./components/FreezerDash";

function App() {
  const { stores, loading } = useStores();
  const [selectedStoreId, setSelectedStoreId] = useState<string | null>(null);

  const selectedStore = stores.find((s) => s.id === selectedStoreId);

  return (
    <div className="app">
      <header>
        <h1>🧊 Freezer Monitor</h1>
        {selectedStore && (
          <p className="subtitle">Viewing: {selectedStore.store_id}</p>
        )}
      </header>
      <div className="layout">
        <StoreList
          stores={stores}
          loading={loading}
          selectedStoreId={selectedStoreId}
          onSelectStore={setSelectedStoreId}
        />
        <main>
          {selectedStoreId ? (
            <FreezerDash storeId={selectedStoreId} />
          ) : (
            <div className="placeholder">
              <p>Select a store to view freezer temperatures</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
