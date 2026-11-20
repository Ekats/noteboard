"""SQLite persistence for clipboard history and memos. No Qt in here, so it
can be tested headless and shared with the future board process."""

import hashlib
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

_MIGRATIONS = [
    # v1
    """
    CREATE TABLE clip (
      id INTEGER PRIMARY KEY,
      content TEXT NOT NULL,
      content_hash TEXT NOT NULL UNIQUE,
      created_at INTEGER NOT NULL,      -- unix ms
      last_used_at INTEGER NOT NULL,    -- unix ms
      pinned INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX clip_recent ON clip(pinned DESC, last_used_at DESC);
    CREATE TABLE memo (
      id TEXT PRIMARY KEY,              -- equals the Memos memo id (CreateMemo accepts ?memoId=), so no remote-id mapping
      content TEXT NOT NULL,            -- markdown; tags are inline #hashtags as in Memos
      pinned INTEGER NOT NULL DEFAULT 0,
      state TEXT NOT NULL DEFAULT 'NORMAL' CHECK (state IN ('NORMAL','ARCHIVED')),
      visibility TEXT NOT NULL DEFAULT 'PRIVATE' CHECK (visibility IN ('PRIVATE','PROTECTED','PUBLIC')),
      create_time INTEGER NOT NULL,
      update_time INTEGER NOT NULL,
      deleted_at INTEGER,               -- tombstone: Memos has no trash, deletes must be remembered until synced
      dirty INTEGER NOT NULL DEFAULT 1, -- local change not yet pushed
      synced_update_time INTEGER        -- server update_time at last sync, for last-write-wins
    );
    CREATE TABLE memo_local (           -- Keep-style fields Memos has no room for; never synced
      memo_id TEXT PRIMARY KEY REFERENCES memo(id) ON DELETE CASCADE,
      title TEXT,
      color TEXT,
      reminder_at INTEGER,
      position INTEGER
    );
    """,
]

_UNSET = object()


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass(frozen=True)
class Clip:
    id: int
    content: str
    created_at: int
    last_used_at: int
    pinned: bool


@dataclass(frozen=True)
class Memo:
    id: str
    content: str
    pinned: bool
    state: str
    visibility: str
    create_time: int
    update_time: int
    title: str | None
    color: str | None
    reminder_at: int | None
    position: int | None


class _Tx:
    """BEGIN IMMEDIATE ... COMMIT, so read-then-write sequences cannot race
    the other process."""

    def __init__(self, db: sqlite3.Connection):
        self._db = db

    def __enter__(self):
        self._db.execute("BEGIN IMMEDIATE")

    def __exit__(self, exc_type, *_):
        self._db.execute("ROLLBACK" if exc_type else "COMMIT")


class Store:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # Autocommit; transactions are explicit so migrations can be atomic.
        self._db = sqlite3.connect(str(path), isolation_level=None)
        self._db.row_factory = sqlite3.Row
        # The popup daemon and the (future, separate-process) board share
        # this file: WAL lets one write while the other reads, and the busy
        # timeout rides out the brief moments both want to write.
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=3000")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def close(self) -> None:
        self._db.close()

    def _migrate(self) -> None:
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        for target, script in enumerate(_MIGRATIONS, start=1):
            if target <= version:
                continue
            # executescript runs the explicit BEGIN/COMMIT as written.
            try:
                self._db.executescript(
                    f"BEGIN;\n{script}\nPRAGMA user_version={target};\nCOMMIT;")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def _tx(self) -> _Tx:
        return _Tx(self._db)

    # -- clips ---------------------------------------------------------

    def add_clip(self, content: str, limit: int) -> int | None:
        if not content.strip():
            return None
        digest = hashlib.sha256(content.encode()).hexdigest()
        now = _now_ms()
        with self._tx():
            row = self._db.execute(
                "SELECT id FROM clip WHERE content_hash = ?", (digest,)).fetchone()
            if row:
                clip_id = row["id"]
                self._db.execute(
                    "UPDATE clip SET last_used_at = ? WHERE id = ?", (now, clip_id))
            else:
                clip_id = self._db.execute(
                    "INSERT INTO clip (content, content_hash, created_at, last_used_at)"
                    " VALUES (?, ?, ?, ?)", (content, digest, now, now)).lastrowid
            self._prune(limit)
        return clip_id

    def clips(self) -> list[Clip]:
        rows = self._db.execute(
            "SELECT id, content, created_at, last_used_at, pinned FROM clip"
            " ORDER BY pinned DESC, last_used_at DESC, id DESC")
        return [Clip(r["id"], r["content"], r["created_at"], r["last_used_at"],
                     bool(r["pinned"])) for r in rows]

    def set_clip_pinned(self, clip_id: int, pinned: bool) -> None:
        self._db.execute("UPDATE clip SET pinned = ? WHERE id = ?",
                         (int(pinned), clip_id))

    def delete_clip(self, clip_id: int) -> None:
        self._db.execute("DELETE FROM clip WHERE id = ?", (clip_id,))

    def prune(self, limit: int) -> None:
        with self._tx():
            self._prune(limit)

    def _prune(self, limit: int) -> None:
        if limit <= 0:  # 0 = unlimited
            return
        self._db.execute(
            "DELETE FROM clip WHERE pinned = 0 AND id NOT IN ("
            " SELECT id FROM clip WHERE pinned = 0"
            " ORDER BY last_used_at DESC, id DESC LIMIT ?)", (limit,))

    # -- memos ---------------------------------------------------------

    def create_memo(self, content: str, *, pinned: bool = False) -> str:
        # Memos ids are believed capped at 32 chars (unverified); a uuid4 hex
        # is exactly 32.
        memo_id = uuid.uuid4().hex
        now = _now_ms()
        self._db.execute(
            "INSERT INTO memo (id, content, pinned, create_time, update_time)"
            " VALUES (?, ?, ?, ?, ?)", (memo_id, content, int(pinned), now, now))
        return memo_id

    def update_memo(self, memo_id: str, *, content: str | None = None,
                    pinned: bool | None = None, state: str | None = None) -> None:
        sets, args = ["update_time = ?", "dirty = 1"], [_now_ms()]
        for column, value in (("content", content),
                              ("pinned", None if pinned is None else int(pinned)),
                              ("state", state)):
            if value is not None:
                sets.append(f"{column} = ?")
                args.append(value)
        self._db.execute(f"UPDATE memo SET {', '.join(sets)} WHERE id = ?",
                         (*args, memo_id))

    def delete_memo(self, memo_id: str) -> None:
        now = _now_ms()
        self._db.execute(
            "UPDATE memo SET deleted_at = ?, update_time = ?, dirty = 1 WHERE id = ?",
            (now, now, memo_id))

    def memos(self, include_archived: bool = False) -> list[Memo]:
        where = "m.deleted_at IS NULL"
        if not include_archived:
            where += " AND m.state = 'NORMAL'"
        rows = self._db.execute(
            "SELECT m.*, l.title, l.color, l.reminder_at, l.position"
            " FROM memo m LEFT JOIN memo_local l ON l.memo_id = m.id"
            f" WHERE {where} ORDER BY m.pinned DESC, m.update_time DESC, m.id")
        return [Memo(r["id"], r["content"], bool(r["pinned"]), r["state"],
                     r["visibility"], r["create_time"], r["update_time"],
                     r["title"], r["color"], r["reminder_at"], r["position"])
                for r in rows]

    def latest_memo(self) -> Memo | None:
        # Not pinned-first like memos(): "latest" means most recently edited.
        r = self._db.execute(
            "SELECT m.*, l.title, l.color, l.reminder_at, l.position"
            " FROM memo m LEFT JOIN memo_local l ON l.memo_id = m.id"
            " WHERE m.deleted_at IS NULL AND m.state = 'NORMAL'"
            " ORDER BY m.update_time DESC, m.id LIMIT 1").fetchone()
        return r and Memo(r["id"], r["content"], bool(r["pinned"]), r["state"],
                          r["visibility"], r["create_time"], r["update_time"],
                          r["title"], r["color"], r["reminder_at"], r["position"])

    def set_memo_local(self, memo_id: str, *, title=_UNSET, color=_UNSET,
                       reminder_at=_UNSET, position=_UNSET) -> None:
        fields = {k: v for k, v in (("title", title), ("color", color),
                                    ("reminder_at", reminder_at),
                                    ("position", position)) if v is not _UNSET}
        with self._tx():
            self._db.execute(
                "INSERT OR IGNORE INTO memo_local (memo_id) VALUES (?)", (memo_id,))
            if fields:
                sets = ", ".join(f"{k} = ?" for k in fields)
                self._db.execute(f"UPDATE memo_local SET {sets} WHERE memo_id = ?",
                                 (*fields.values(), memo_id))
