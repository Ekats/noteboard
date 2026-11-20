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
    # v2
    """
    CREATE TABLE draft (                -- the capture pad's unsent text; never synced
      id INTEGER PRIMARY KEY CHECK (id = 1),
      content TEXT NOT NULL,
      update_time INTEGER NOT NULL
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


@dataclass(frozen=True)
class SyncRow:
    """A memo row as the sync sees it. Doubles as the optimistic-lock token:
    a write guarded by `base` is skipped if the row changed since it was read."""
    id: str
    content: str
    pinned: bool
    state: str
    visibility: str
    create_time: int
    update_time: int
    deleted_at: int | None
    dirty: bool
    synced_update_time: int | None


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
        # Called after a local memo write that sync should push. The sync
        # worker's own writes (apply_remote etc.) deliberately do not call it.
        self.on_memo_change = None
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
        self._memo_changed()
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
        self._memo_changed()

    def delete_memo(self, memo_id: str) -> None:
        now = _now_ms()
        self._db.execute(
            "UPDATE memo SET deleted_at = ?, update_time = ?, dirty = 1 WHERE id = ?",
            (now, now, memo_id))
        self._memo_changed()

    def _memo_changed(self) -> None:
        if self.on_memo_change:
            self.on_memo_change()

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

    # -- draft ---------------------------------------------------------

    def draft(self) -> str:
        r = self._db.execute("SELECT content FROM draft WHERE id = 1").fetchone()
        return r["content"] if r else ""

    def set_draft(self, text: str) -> None:
        self._db.execute(
            "INSERT INTO draft (id, content, update_time) VALUES (1, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET content = excluded.content,"
            " update_time = excluded.update_time", (text, _now_ms()))

    def send_draft(self) -> str | None:
        """Turn the draft into a memo and empty it; None if it is blank."""
        with self._tx():
            text = self.draft().strip()
            if not text:
                return None
            memo_id = self.create_memo(text)
            self.set_draft("")
        return memo_id

    # -- memo local fields ---------------------------------------------

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

    # -- sync ----------------------------------------------------------
    # Every write takes the SyncRow the decision was based on and re-reads the
    # row inside BEGIN IMMEDIATE: if the user edited it meanwhile the write is
    # skipped (returns False/None) and the row stays dirty for the next run.

    def sync_rows(self) -> list[SyncRow]:
        return [self._to_sync_row(r) for r in self._db.execute(
            "SELECT * FROM memo ORDER BY id")]

    @staticmethod
    def _to_sync_row(r: sqlite3.Row) -> SyncRow:
        return SyncRow(r["id"], r["content"], bool(r["pinned"]), r["state"],
                       r["visibility"], r["create_time"], r["update_time"],
                       r["deleted_at"], bool(r["dirty"]), r["synced_update_time"])

    def _current(self, memo_id: str) -> SyncRow | None:
        r = self._db.execute("SELECT * FROM memo WHERE id = ?", (memo_id,)).fetchone()
        return self._to_sync_row(r) if r else None

    def _write_remote(self, memo_id: str, r) -> None:
        self._db.execute(
            "UPDATE memo SET content = ?, pinned = ?, state = ?, visibility = ?,"
            " create_time = ?, update_time = ?, deleted_at = NULL, dirty = 0,"
            " synced_update_time = ? WHERE id = ?",
            (r.content, int(r.pinned), r.state, r.visibility, r.create_time,
             r.update_time, r.update_time, memo_id))

    def insert_remote(self, r) -> bool:
        with self._tx():
            if self._current(r.id):
                return False
            self._db.execute(
                "INSERT INTO memo (id, content, pinned, state, visibility,"
                " create_time, update_time, dirty, synced_update_time)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                (r.id, r.content, int(r.pinned), r.state, r.visibility,
                 r.create_time, r.update_time, r.update_time))
        return True

    def apply_remote(self, base: SyncRow, r) -> bool:
        """Overwrite the row with the server version; memo_local is untouched.
        Also revives a tombstone (an edit beats a delete)."""
        with self._tx():
            if self._current(base.id) != base:
                return False
            self._write_remote(base.id, r)
        return True

    def mark_synced(self, base: SyncRow, r) -> bool:
        with self._tx():
            if self._current(base.id) != base:
                return False
            self._db.execute(
                "UPDATE memo SET dirty = 0, synced_update_time = ? WHERE id = ?",
                (r.update_time, base.id))
        return True

    def hard_delete(self, base: SyncRow) -> bool:
        with self._tx():
            if self._current(base.id) != base:
                return False
            self._db.execute("DELETE FROM memo WHERE id = ?", (base.id,))
        return True

    def duplicate_as_new(self, base: SyncRow, r) -> SyncRow | None:
        """Conflict, keep both: the local version moves to a new never-synced
        dirty row (memo_local copied), the original id takes the server's."""
        new_id = uuid.uuid4().hex
        with self._tx():
            if self._current(base.id) != base:
                return None
            self._db.execute(
                "INSERT INTO memo (id, content, pinned, state, visibility,"
                " create_time, update_time, dirty)"
                " SELECT ?, content, pinned, state, visibility, create_time, ?, 1"
                " FROM memo WHERE id = ?", (new_id, _now_ms(), base.id))
            self._db.execute(
                "INSERT INTO memo_local (memo_id, title, color, reminder_at, position)"
                " SELECT ?, title, color, reminder_at, position FROM memo_local"
                " WHERE memo_id = ?", (new_id, base.id))
            self._write_remote(base.id, r)
            return self._current(new_id)

    def finish_push(self, base: SyncRow, r, keep_local: bool = False) -> bool:
        """Record the server's answer to a create/PATCH of `base`. If the
        server assigned another id the row (and its memo_local) moves to it.
        True if the row ended clean; False if it was edited during the push,
        in which case the local fields win and it stays dirty (also forced by
        keep_local, for a push that only half landed)."""
        with self._tx():
            cur = self._current(base.id)
            if cur is None:
                return False
            if r.id != base.id:
                self._move_id(base.id, r.id)
            if keep_local or cur.update_time != base.update_time:
                self._db.execute(
                    "UPDATE memo SET synced_update_time = ?, dirty = 1 WHERE id = ?",
                    (r.update_time, r.id))
                return False
            self._write_remote(r.id, r)
        return True

    def _move_id(self, old: str, new: str) -> None:
        # No ON UPDATE CASCADE: insert the parent under the new id, repoint
        # the child, then drop the old parent.
        self._db.execute(
            "INSERT INTO memo (id, content, pinned, state, visibility, create_time,"
            " update_time, deleted_at, dirty, synced_update_time)"
            " SELECT ?, content, pinned, state, visibility, create_time, update_time,"
            " deleted_at, dirty, synced_update_time FROM memo WHERE id = ?", (new, old))
        self._db.execute("UPDATE memo_local SET memo_id = ? WHERE memo_id = ?", (new, old))
        self._db.execute("DELETE FROM memo WHERE id = ?", (old,))
