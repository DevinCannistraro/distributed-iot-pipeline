import { initializeApp } from "firebase/app";
import { getFirestore, connectFirestoreEmulator } from "firebase/firestore";

const app = initializeApp({ projectId: "local-dev" });
const db = getFirestore(app);

if (import.meta.env.DEV) {
  connectFirestoreEmulator(db, "localhost", 8080);
}

export { db };
