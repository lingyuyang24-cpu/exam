"""Small durable store. Every operation has a short-lived connection/transaction."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid4())


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, cli_session_id TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                run_id TEXT, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                request_id TEXT NOT NULL, prompt TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                exit_code INTEGER, error TEXT, usage TEXT,
                UNIQUE(session_id, request_id)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs(session_id)
                WHERE status IN ('queued', 'running');
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
                type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS run_events ON events(run_id, id);
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                run_id TEXT NOT NULL REFERENCES runs(id), name TEXT NOT NULL,
                relative_path TEXT NOT NULL, size INTEGER NOT NULL,
                sha256 TEXT NOT NULL, partial INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def all(self, sql, args=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def execute(self, sql, args=()):
        with self.connect() as db:
            return db.execute(sql, args).rowcount

    def create_session(self, title):
        sid, stamp = uid(), now()
        self.execute("INSERT INTO sessions VALUES (?, ?, NULL, ?, ?)", (sid, title, stamp, stamp))
        return self.one("SELECT * FROM sessions WHERE id=?", (sid,))

    def sessions(self):
        return self.all("""SELECT s.*,
            (SELECT status FROM runs WHERE session_id=s.id ORDER BY created_at DESC LIMIT 1) AS status,
            (SELECT content FROM messages WHERE session_id=s.id AND role='user'
                ORDER BY created_at DESC LIMIT 1) AS preview,
            (SELECT COUNT(*) FROM messages WHERE session_id=s.id) AS message_count
            FROM sessions s ORDER BY updated_at DESC""")

    def enqueue(self, sid, request_id, prompt):
        """Idempotency lookup and active-run exclusion happen in one transaction."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM runs WHERE session_id=? AND request_id=?", (sid, request_id)).fetchone()
            if old:
                return dict(old), False
            if db.execute("SELECT id FROM runs WHERE session_id=? AND status IN ('queued','running')", (sid,)).fetchone():
                raise ValueError("当前会话还有任务在执行，请等待完成或先停止。")
            rid, stamp = uid(), now()
            db.execute("INSERT INTO runs(id,session_id,request_id,prompt,status,created_at) VALUES(?,?,?,?,'queued',?)",
                       (rid, sid, request_id, prompt, stamp))
            db.execute("INSERT INTO messages VALUES(?,?,?,'user',?,?)", (uid(), sid, rid, prompt, stamp))
            db.execute("UPDATE sessions SET updated_at=?, title=CASE WHEN title='新会话' THEN ? ELSE title END WHERE id=?",
                       (stamp, prompt[:28], sid))
            return dict(db.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()), True

    def event(self, rid, kind, payload):
        stamp = now()
        with self.connect() as db:
            cursor = db.execute("INSERT INTO events(run_id,type,payload,created_at) VALUES(?,?,?,?)",
                                (rid, kind, json.dumps(payload, ensure_ascii=False), stamp))
            return {"id": cursor.lastrowid, "run_id": rid, "type": kind, "payload": payload, "created_at": stamp}

    def events(self, rid, after=0, limit=250):
        rows = self.all("SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id LIMIT ?", (rid, after, limit))
        for row in rows:
            row["payload"] = json.loads(row["payload"])
        return rows
