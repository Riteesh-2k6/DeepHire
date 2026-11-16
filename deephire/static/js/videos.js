// Answer recordings live only in this browser (IndexedDB). They are never uploaded.
const DB = 'deephire', STORE = 'takes';

function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function run(mode, fn) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const req = fn(tx.objectStore(STORE));
    tx.oncomplete = () => resolve(req && req.result);
    tx.onerror = () => reject(tx.error);
  });
}

const key = (sessionId, index) => `${sessionId}:${index}`;
export const saveTake = (s, i, blob) => run('readwrite', st => st.put(blob, key(s, i)));
export const loadTake = (s, i) => run('readonly', st => st.get(key(s, i))).catch(() => null);
export const deleteTake = (s, i) => run('readwrite', st => st.delete(key(s, i)));
// Every recording of one session (its main answers and follow-ups).
export const deleteSessionTakes = s => run('readwrite', st => st.delete(IDBKeyRange.bound(`${s}:`, `${s}:￿`)));
