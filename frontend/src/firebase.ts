import { initializeApp } from "firebase/app";
import { getFirestore, connectFirestoreEmulator } from "firebase/firestore";

const projectId = import.meta.env.VITE_FIREBASE_PROJECT_ID ?? "local-dev";

const app = initializeApp({ projectId });
const db = getFirestore(app);

if (import.meta.env.DEV) {
  connectFirestoreEmulator(db, "localhost", 8080);
}

export { db };
