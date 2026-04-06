import { useEffect, useState } from "react";
import { collection, onSnapshot, Timestamp } from "firebase/firestore";
import { db } from "../firebase";

export interface Freezer {
  id: string;
  freezer_id: string;
  temp_c: number;
  reading_time: Date;
  received_at: Date;
  device_id: string;
}

function toDate(val: unknown): Date {
  if (val instanceof Timestamp) return val.toDate();
  if (val instanceof Date) return val;
  return new Date(val as string);
}

export function useFreezersByStore(storeId: string | null) {
  const [freezers, setFreezers] = useState<Freezer[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!storeId) {
      setFreezers([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    const unsubscribe = onSnapshot(
      collection(db, "stores", storeId, "freezers"),
      (snapshot) => {
        const list = snapshot.docs.map((doc) => {
          const d = doc.data();
          return {
            id: doc.id,
            freezer_id: d.freezer_id || doc.id,
            temp_c: d.temp_c,
            reading_time: toDate(d.reading_time),
            received_at: toDate(d.received_at),
            device_id: d.device_id || "",
          };
        });
        setFreezers(list);
        setLoading(false);
      },
    );
    return () => unsubscribe();
  }, [storeId]);

  return { freezers, loading };
}
