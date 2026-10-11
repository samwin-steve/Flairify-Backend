"""Owner-scoped records. Local SQLite is durable; Firestore uses identical contracts."""

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from functools import lru_cache
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

    def list(self, kind, owner):
        if self.cloud:
            from google.cloud.firestore_v1.base_query import FieldFilter

            return [
                s.to_dict()["data"]
                for s in self.db.collection("flairify_" + kind)
                .where(filter=FieldFilter("owner", "==", owner))
                .stream()
            ]
        with self.lock:
            rows = self.db.execute(
                "SELECT data FROM records WHERE kind=? AND owner=? ORDER BY rowid", (kind, owner)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

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

    def delete(self, kind, owner, key):
        if self.cloud:
            self.ref(kind, owner, key).delete()
        else:
            with self.lock:
                self.db.execute("DELETE FROM records WHERE kind=? AND owner=? AND id=?", (kind, owner, key))
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
