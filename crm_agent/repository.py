"""SQLite persistence, optimistic concurrency, and append-only audit events."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from crm_agent.models import Contact


class ConflictError(ValueError):
    """A stale version or invalid state transition was rejected."""


class Repository:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with sqlite3.connect(self.path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            yield db

    def initialize(self) -> None:
        with self.transaction() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS contacts (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS objects (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
                event TEXT NOT NULL, contact_id TEXT, details TEXT NOT NULL
            );
            """)

    @staticmethod
    def audit(db: sqlite3.Connection, event: str, contact_id: str | None, details: dict) -> None:
        db.execute(
            "INSERT INTO audit(timestamp,event,contact_id,details) VALUES (?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), event, contact_id, json.dumps(details)),
        )

    def seed(self, contacts: list[Contact]) -> None:
        with self.transaction() as db:
            if db.execute("SELECT count(*) FROM contacts").fetchone()[0]:
                return
            db.executemany(
                "INSERT INTO contacts VALUES (?,?)",
                [(c.contact_id, c.model_dump_json()) for c in contacts],
            )
            self.audit(db, "synthetic_seed", None, {"count": len(contacts)})

    def contacts(self) -> list[Contact]:
        with self.transaction() as db:
            return [
                Contact.model_validate_json(row[0])
                for row in db.execute("SELECT payload FROM contacts ORDER BY id")
            ]

    def contact(self, contact_id: str, db: sqlite3.Connection | None = None) -> Contact:
        if db is None:
            with self.transaction() as connection:
                return self.contact(contact_id, connection)
        row = db.execute("SELECT payload FROM contacts WHERE id=?", (contact_id,)).fetchone()
        if row is None:
            raise KeyError("Contact not found")
        return Contact.model_validate_json(row[0])

    def save_contact(self, c: Contact, create: bool = False) -> Contact:
        with self.transaction() as db:
            if create:
                if db.execute("SELECT 1 FROM contacts WHERE id=?", (c.contact_id,)).fetchone():
                    raise ConflictError("Contact already exists")
                c = c.model_copy(update={"version": 1})
                db.execute("INSERT INTO contacts VALUES (?,?)", (c.contact_id, c.model_dump_json()))
            else:
                previous = self.contact(c.contact_id, db)
                if previous.version != c.version:
                    raise ConflictError("Contact changed; reload its current version")
                c = c.model_copy(update={"version": previous.version + 1})
                db.execute(
                    "UPDATE contacts SET payload=? WHERE id=?", (c.model_dump_json(), c.contact_id)
                )
            self.audit(
                db,
                "contact_created" if create else "contact_updated",
                c.contact_id,
                {"version": c.version},
            )
            return c

    def put_object(
        self, kind: str, payload: dict[str, Any], db: sqlite3.Connection | None = None
    ) -> dict:
        if db is None:
            with self.transaction() as connection:
                return self.put_object(kind, payload, connection)
        value = {**payload, "id": payload.get("id", str(uuid4()))}
        db.execute(
            "INSERT INTO objects VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
            (value["id"], kind, json.dumps(value)),
        )
        return value

    def object(self, object_id: str, kind: str, db: sqlite3.Connection | None = None) -> dict:
        if db is None:
            with self.transaction() as connection:
                return self.object(object_id, kind, connection)
        row = db.execute(
            "SELECT payload FROM objects WHERE id=? AND kind=?", (object_id, kind)
        ).fetchone()
        if row is None:
            raise KeyError(f"{kind.capitalize()} not found")
        return json.loads(row[0])

    def objects(self, kind: str, db: sqlite3.Connection | None = None) -> list[dict]:
        if db is None:
            with self.transaction() as connection:
                return self.objects(kind, connection)
        return [
            json.loads(row[0])
            for row in db.execute(
                "SELECT payload FROM objects WHERE kind=? ORDER BY rowid", (kind,)
            )
        ]

    def events(self) -> list[dict]:
        with self.transaction() as db:
            return [
                {**dict(row), "details": json.loads(row["details"])}
                for row in db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 500")
            ]
