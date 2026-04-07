import { useState, useRef, useEffect, useId } from "react";
import type { Store } from "../hooks/useStores";

interface StoreSelectorProps {
  stores: Store[];
  loading: boolean;
  selectedStoreId: string | null;
  onSelectStore: (storeId: string) => void;
}

export function StoreSelector({
  stores,
  loading,
  selectedStoreId,
  onSelectStore,
}: StoreSelectorProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();

  const selectedStore = stores.find((s) => s.id === selectedStoreId);

  const filtered = query
    ? stores.filter((s) =>
        s.store_id.toLowerCase().includes(query.toLowerCase()),
      )
    : stores;

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    setQuery(e.target.value);
    setOpen(true);
    setHighlightedIndex(0);
  }

  function handleFocus() {
    setOpen(true);
  }

  function handleSelect(store: Store) {
    onSelectStore(store.id);
    setQuery("");
    setOpen(false);
    inputRef.current?.blur();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "Enter") setOpen(true);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filtered[highlightedIndex]) handleSelect(filtered[highlightedIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
    }
  }

  // Scroll highlighted item into view
  useEffect(() => {
    if (!listRef.current) return;
    const item = listRef.current.children[highlightedIndex] as HTMLElement;
    item?.scrollIntoView({ block: "nearest" });
  }, [highlightedIndex]);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        inputRef.current &&
        !inputRef.current.closest(".store-selector")?.contains(e.target as Node)
      ) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const placeholder = loading
    ? "Loading stores…"
    : selectedStore
      ? selectedStore.store_id
      : "Search or select a store…";

  return (
    <div className="store-selector">
      <label className="store-selector-label">Store</label>
      <div className="store-selector-input-wrap">
        <input
          ref={inputRef}
          type="text"
          className="store-selector-input"
          placeholder={placeholder}
          value={query}
          disabled={loading}
          onChange={handleInputChange}
          onFocus={handleFocus}
          onKeyDown={handleKeyDown}
          aria-autocomplete="list"
          aria-controls={listId}
          aria-expanded={open}
          role="combobox"
          autoComplete="off"
          spellCheck={false}
        />
        <span className="store-selector-chevron" aria-hidden>
          {open ? "▲" : "▼"}
        </span>
      </div>

      {open && filtered.length > 0 && (
        <ul
          id={listId}
          ref={listRef}
          className="store-selector-dropdown"
          role="listbox"
        >
          {filtered.map((store, i) => (
            <li
              key={store.id}
              role="option"
              aria-selected={store.id === selectedStoreId}
              className={[
                "store-selector-option",
                store.id === selectedStoreId ? "selected" : "",
                i === highlightedIndex ? "highlighted" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onMouseDown={(e) => {
                e.preventDefault(); // keep focus on input until select
                handleSelect(store);
              }}
              onMouseEnter={() => setHighlightedIndex(i)}
            >
              {store.store_id}
            </li>
          ))}
        </ul>
      )}

      {open && filtered.length === 0 && !loading && (
        <div className="store-selector-empty">No stores match "{query}"</div>
      )}
    </div>
  );
}

