"""Owner-scoped records. Local SQLite is durable; Firestore uses identical contracts."""

import hashlib
import json
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

from .config import settings


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        cfg = settings()
        self.cloud = cfg.store_backend == "firestore"
        if self.cloud:
            from google.cloud import firestore

            self.db = firestore.Client(project=cfg.google_cloud_project, database=cfg.firestore_database)
        else:
            Path(cfg.data_dir).mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(str(Path(cfg.data_dir) / "flairify.db"), check_same_thread=False)
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS records (kind TEXT, owner TEXT, id TEXT, data TEXT, PRIMARY KEY(kind,owner,id))"
            )
            self.db.commit()

    def ref(self, kind, owner, key):
        return self.db.collection("flairify_" + kind).document(
            hashlib.sha256(f"{owner}:{key}".encode()).hexdigest()
        )

    def get(self, kind, owner, key):
        if self.cloud:
            s = self.ref(kind, owner, key).get()
            return s.to_dict()["data"] if s.exists else None
        with self.lock:
            r = self.db.execute(
                "SELECT data FROM records WHERE kind=? AND owner=? AND id=?", (kind, owner, key)
            ).fetchone()
        return json.loads(r[0]) if r else None

    def list(self, kind, owner, *, fields=None):
        if self.cloud:
            from google.cloud.firestore_v1.base_query import FieldFilter

            query = self.db.collection("flairify_" + kind).where(filter=FieldFilter("owner", "==", owner))
            if fields:
                query = query.select(["data." + name for name in fields])
            return [s.to_dict()["data"] for s in query.stream()]
        with self.lock:
            rows = self.db.execute(
                "SELECT data FROM records WHERE kind=? AND owner=? ORDER BY rowid", (kind, owner)
            ).fetchall()
        values = [json.loads(r[0]) for r in rows]
        return [{k: v for k, v in row.items() if k in fields} for row in values] if fields else values

    def get_many(self, kind, owner, keys, *, fields=None):
        if self.cloud:
            refs = [self.ref(kind, owner, key) for key in dict.fromkeys(keys)]
            if not refs:
                return []
            mask = ["data." + name for name in fields] if fields else None
            return [snap.to_dict()["data"] for snap in self.db.get_all(refs, field_paths=mask) if snap.exists]
        values = [self.get(kind, owner, key) for key in dict.fromkeys(keys)]
        return [{k: v for k, v in row.items() if not fields or k in fields} for row in values if row]

    def put(self, kind, owner, key, data):
        if self.cloud:
            self.ref(kind, owner, key).set({"owner": owner, "id": key, "data": data})
        else:
            with self.lock:
                self.db.execute(
                    "INSERT OR REPLACE INTO records VALUES (?,?,?,?)", (kind, owner, key, json.dumps(data))
                )
                self.db.commit()
        return data

    def put_many(self, records):
        """Batch bounded graph writes without one network round trip per edge."""
        unique = {(kind, owner, key): value for kind, owner, key, value in records}
        if self.cloud:
            entries = list(unique.items())
            for start in range(0, len(entries), 400):
                batch = self.db.batch()
                for (kind, owner, key), value in entries[start : start + 400]:
                    batch.set(self.ref(kind, owner, key), {"owner": owner, "id": key, "data": value})
                batch.commit()
        else:
            with self.lock:
                self.db.executemany(
                    "INSERT OR REPLACE INTO records VALUES (?,?,?,?)",
                    [(k, o, i, json.dumps(v)) for (k, o, i), v in unique.items()],
                )
                self.db.commit()

    def delete(self, kind, owner, key):
        if self.cloud:
            self.ref(kind, owner, key).delete()
        else:
            with self.lock:
                self.db.execute("DELETE FROM records WHERE kind=? AND owner=? AND id=?", (kind, owner, key))
                self.db.commit()

    def create_missing(self, kind, owner, records):
        """Bulk fixture bootstrap without replacing seller records or concurrent writes."""
        if self.cloud:
            from google.api_core.exceptions import AlreadyExists

            for start in range(0, len(records), 200):
                group = records[start : start + 200]
                batch = self.db.batch()
                for value in group:
                    batch.create(
                        self.ref(kind, owner, value["id"]), {"owner": owner, "id": value["id"], "data": value}
                    )
                try:
                    batch.commit()
                except AlreadyExists:
                    # Another request may have seeded concurrently. Never overwrite it.
                    for value in group:
                        try:
                            self.ref(kind, owner, value["id"]).create(
                                {"owner": owner, "id": value["id"], "data": value}
                            )
                        except AlreadyExists:
                            pass
        else:
            with self.lock:
                self.db.executemany(
                    "INSERT OR IGNORE INTO records VALUES (?,?,?,?)",
                    [(kind, owner, v["id"], json.dumps(v)) for v in records],
                )
                self.db.commit()

    def mutate(self, kind, owner, key, fn):
        """Transactionally transform one record (quotas, job lease, idempotency)."""
        if self.cloud:
            from google.cloud import firestore

            ref = self.ref(kind, owner, key)

            @firestore.transactional
            def update(tx):
                snap = ref.get(transaction=tx)
                value = fn(snap.to_dict()["data"] if snap.exists else None)
                tx.set(ref, {"owner": owner, "id": key, "data": value})
                return value

            return update(self.db.transaction())
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute(
                    "SELECT data FROM records WHERE kind=? AND owner=? AND id=?", (kind, owner, key)
                ).fetchone()
                value = fn(json.loads(row[0]) if row else None)
                self.db.execute(
                    "INSERT OR REPLACE INTO records VALUES (?,?,?,?)", (kind, owner, key, json.dumps(value))
                )
                self.db.commit()
                return value
            except Exception:
                self.db.rollback()
                raise


@lru_cache
def store():
    return Store()
