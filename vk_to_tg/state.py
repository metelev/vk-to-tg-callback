import json
from pathlib import Path
import sqlite3
import time


class State:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS jobs (
                key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT NOT NULL DEFAULT '',
                result TEXT,
                created_at REAL NOT NULL
            );
        """)

    def close(self) -> None:
        self.db.close()

    def enqueue(self, key: str, payload: dict) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO jobs(key,payload,created_at) VALUES(?,?,?)",
                (key, json.dumps(payload, ensure_ascii=False), time.time()),
            )

    def pending(self) -> list[dict]:
        return self._rows("WHERE status='pending'")

    def list_jobs(self) -> list[dict]:
        return self._rows("")

    def _rows(self, clause: str) -> list[dict]:
        rows = self.db.execute(f"SELECT * FROM jobs {clause} ORDER BY created_at").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            item["result"] = json.loads(item["result"]) if item["result"] else None
            result.append(item)
        return result

    def set_status(self, key: str, status: str, error: str = "") -> None:
        with self.db:
            self.db.execute("UPDATE jobs SET status=?,error=? WHERE key=?", (status, error, key))

    def complete(self, key: str, result) -> None:
        with self.db:
            self.db.execute(
                "UPDATE jobs SET status='done',error='',result=? WHERE key=?",
                (json.dumps(result, ensure_ascii=False), key),
            )

    def recover(self) -> None:
        with self.db:
            self.db.execute(
                "UPDATE jobs SET status='uncertain',error='stopped during Telegram delivery' "
                "WHERE status='sending'"
            )
