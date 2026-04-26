from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone


class LocalStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS decision_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS twelvelabs_ingestion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source_key TEXT,
                    status TEXT NOT NULL,
                    index_id TEXT,
                    asset_id TEXT,
                    indexed_asset_id TEXT,
                    video_id TEXT,
                    stream_url TEXT,
                    search_reference TEXT,
                    error TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cloudinary_event_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    public_id TEXT,
                    resource_type TEXT,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )

    def save_decision(self, payload: dict) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO decision_log (created_at, payload) VALUES (?, ?)",
                (datetime.now(timezone.utc).isoformat(), json.dumps(payload)),
            )

    def latest(self, limit: int = 10) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT created_at, payload FROM decision_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [{"created_at": row[0], "payload": json.loads(row[1])} for row in rows]

    def save_twelvelabs_ingestion(self, payload: dict) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO twelvelabs_ingestion_log (
                    created_at,
                    source_key,
                    status,
                    index_id,
                    asset_id,
                    indexed_asset_id,
                    video_id,
                    stream_url,
                    search_reference,
                    error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    payload.get("source_key"),
                    payload.get("status", "unknown"),
                    payload.get("index_id"),
                    payload.get("asset_id"),
                    payload.get("indexed_asset_id"),
                    payload.get("video_id"),
                    payload.get("stream_url"),
                    payload.get("search_reference"),
                    payload.get("error"),
                ),
            )

    def latest_twelvelabs_ingestion(self, limit: int = 20) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT created_at, source_key, status, index_id, asset_id, indexed_asset_id, video_id,
                       stream_url, search_reference, error
                FROM twelvelabs_ingestion_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        keys = [
            "created_at",
            "source_key",
            "status",
            "index_id",
            "asset_id",
            "indexed_asset_id",
            "video_id",
            "stream_url",
            "search_reference",
            "error",
        ]
        return [dict(zip(keys, row)) for row in rows]

    def save_cloudinary_event(self, result: dict) -> int:
        """Persist webhook processing result. Returns new row id."""
        with self._connect() as connection:
            cur = connection.execute(
                """
                INSERT INTO cloudinary_event_log (created_at, public_id, resource_type, status, result_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    (result or {}).get("public_id") or (result or {}).get("publicId"),
                    (result or {}).get("resource_type"),
                    (result or {}).get("status", "unknown"),
                    json.dumps(result, ensure_ascii=True),
                ),
            )
            return int(cur.lastrowid)

    def latest_cloudinary_event(self) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, created_at, public_id, resource_type, status, result_json
                FROM cloudinary_event_log
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "created_at": row[1],
            "public_id": row[2],
            "resource_type": row[3],
            "status": row[4],
            "result": json.loads(row[5]),
        }

    def list_cloudinary_events(self, limit: int = 20) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, public_id, resource_type, status, result_json
                FROM cloudinary_event_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            out.append(
                {
                    "id": row[0],
                    "created_at": row[1],
                    "public_id": row[2],
                    "resource_type": row[3],
                    "status": row[4],
                    "result": json.loads(row[5]),
                }
            )
        return out
