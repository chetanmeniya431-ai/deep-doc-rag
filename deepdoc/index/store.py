"""SQLite store: documents, parsed elements, chunks, a BM25 keyword index (FTS5)
and embedding vectors. One file, no server, nothing to pay for."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager

import numpy as np

from .. import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE, path TEXT, title TEXT, pages INTEGER,
    status TEXT, message TEXT, stats TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS elements (
    id INTEGER PRIMARY KEY, doc_id INTEGER, page INTEGER, ord INTEGER, kind TEXT, col INTEGER,
    bbox TEXT, text TEXT, section TEXT, meta TEXT
);
CREATE INDEX IF NOT EXISTS elements_page ON elements(doc_id, page);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY, doc_id INTEGER, seq INTEGER, kind TEXT, section TEXT, pages TEXT,
    boxes TEXT, text TEXT, embed_text TEXT, meta TEXT, vector BLOB
);
CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(doc_id, seq);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(embed_text, content='chunks', content_rowid='id',
    tokenize='porter unicode61');
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, embed_text) VALUES (new.id, new.embed_text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, embed_text) VALUES ('delete', old.id, old.embed_text);
END;
"""

_lock = threading.Lock()
_matrix_cache: dict = {}


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    con = sqlite3.connect(str(config.DB_PATH), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


@contextmanager
def db():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


def invalidate_cache() -> None:
    with _lock:
        _matrix_cache.clear()


def vectors() -> tuple[np.ndarray, list[int]]:
    """All chunk vectors as one normalised matrix (cached until the index changes)."""
    with _lock:
        if "m" in _matrix_cache:
            return _matrix_cache["m"], _matrix_cache["ids"]
        with db() as con:
            rows = con.execute("SELECT id, vector FROM chunks WHERE vector IS NOT NULL ORDER BY id").fetchall()
        ids = [r["id"] for r in rows]
        m = np.vstack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows]) if rows else np.zeros((0, 1), np.float32)
        _matrix_cache.update(m=m, ids=ids)
        return m, ids


def chunk_rows(ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    with db() as con:
        q = f"SELECT c.*, d.name AS doc_name, d.title AS doc_title FROM chunks c JOIN documents d ON d.id = c.doc_id " \
            f"WHERE c.id IN ({','.join('?' * len(ids))})"
        out = {}
        for r in con.execute(q, ids).fetchall():
            row = dict(r)
            row.pop("vector", None)
            row["pages"] = json.loads(row["pages"])
            row["boxes"] = json.loads(row["boxes"])
            row["meta"] = json.loads(row["meta"] or "{}")
            out[row["id"]] = row
        return out
