import { useEffect, useState } from "react";
import { collection, onSnapshot } from "firebase/firestore";
import { db } from "../firebase";

export interface Store {
  id: string;
  store_id: string;
}

export function useStores() {
  const [stores, setStores] = useState<Store[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = onSnapshot(collection(db, "stores"), (snapshot) => {
      const list = snapshot.docs.map((doc) => ({
        id: doc.id,
        store_id: doc.data().store_id || doc.id,
      }));
      setStores(list);
      setLoading(false);
    });
    return () => unsubscribe();
  }, []);

  return { stores, loading };
}
