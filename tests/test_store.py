import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from noteboard import store as store_mod
from noteboard.store import Store

SCRATCH = Path.home() / ".mco" / "scratch"


class Clock:
    """Strictly increasing fake for _now_ms so ordering is deterministic."""

    def __init__(self):
        self.t = 1000

    def __call__(self):
        self.t += 10
        return self.t


class StoreTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(store_mod, "_now_ms", Clock())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.s = Store(":memory:")
        self.addCleanup(self.s.close)

    def contents(self):
        return [c.content for c in self.s.clips()]

    def test_dedupe_bumps_to_top(self):
        a = self.s.add_clip("a", 0)
        self.s.add_clip("b", 0)
        self.assertEqual(self.s.add_clip("a", 0), a)
        self.assertEqual(self.contents(), ["a", "b"])

    def test_recopy_moves_row_without_adding_one(self):
        # Pasting an entry copies it back, which must not create a new row.
        pinned = self.s.add_clip("pinned", 0)
        self.s.set_clip_pinned(pinned, True)
        old = self.s.add_clip("old", 0)
        self.s.add_clip("mid", 0)
        self.s.add_clip("new", 0)
        self.assertEqual(self.s.add_clip("old", 0), old)
        self.assertEqual(len(self.s.clips()), 4)
        # Pinned rows keep their group; the bump is within the unpinned one.
        self.assertEqual(self.contents(), ["pinned", "old", "new", "mid"])

    def test_empty_ignored(self):
        self.assertIsNone(self.s.add_clip("", 0))
        self.assertIsNone(self.s.add_clip(" \n\t", 0))
        self.assertEqual(self.s.clips(), [])

    def test_prune_keeps_newest_and_pinned(self):
        oldest = self.s.add_clip("old", 0)
        self.s.set_clip_pinned(oldest, True)
        for t in "abcd":
            self.s.add_clip(t, 2)
        self.assertEqual(self.contents(), ["old", "d", "c"])

    def test_limit_zero_keeps_all(self):
        for i in range(20):
            self.s.add_clip(str(i), 0)
        self.assertEqual(len(self.s.clips()), 20)

    def test_lowering_limit_deletes(self):
        for i in range(10):
            self.s.add_clip(str(i), 0)
        self.s.prune(3)
        self.assertEqual(self.contents(), ["9", "8", "7"])

    def test_pinned_first(self):
        a = self.s.add_clip("a", 0)
        self.s.add_clip("b", 0)
        self.s.set_clip_pinned(a, True)
        self.assertEqual(self.contents(), ["a", "b"])

    def test_delete_clip(self):
        a = self.s.add_clip("a", 0)
        self.s.delete_clip(a)
        self.assertEqual(self.s.clips(), [])

    def test_memo_create_update_marks_dirty(self):
        mid = self.s.create_memo("hello #x")
        self.assertEqual(len(mid), 32)
        self.s._db.execute("UPDATE memo SET dirty = 0")
        before = self.s.memos()[0]
        self.s.update_memo(mid, content="changed", pinned=True)
        after = self.s.memos()[0]
        self.assertEqual((after.content, after.pinned), ("changed", True))
        self.assertGreater(after.update_time, before.update_time)
        dirty = self.s._db.execute("SELECT dirty FROM memo").fetchone()[0]
        self.assertEqual(dirty, 1)

    def test_pin_without_touch_keeps_time_and_marks_dirty(self):
        a = self.s.create_memo("a")
        self.s.create_memo("b")
        self.s._db.execute("UPDATE memo SET dirty = 0")
        before = {m.id: m.update_time for m in self.s.memos()}
        self.s.update_memo(a, pinned=True, touch=False)
        memos = self.s.memos()
        self.assertEqual([m.content for m in memos], ["a", "b"])
        self.assertEqual(memos[0].update_time, before[a])
        self.assertEqual(self.s._db.execute(
            "SELECT dirty FROM memo WHERE id = ?", (a,)).fetchone()[0], 1)

    def test_delete_memo_is_tombstone(self):
        mid = self.s.create_memo("x")
        self.s.delete_memo(mid)
        self.assertEqual(self.s.memos(include_archived=True), [])
        row = self.s._db.execute(
            "SELECT deleted_at, dirty FROM memo WHERE id = ?", (mid,)).fetchone()
        self.assertIsNotNone(row["deleted_at"])
        self.assertEqual(row["dirty"], 1)

    def test_archived_hidden_unless_requested(self):
        mid = self.s.create_memo("x")
        self.s.update_memo(mid, state="ARCHIVED")
        self.assertEqual(self.s.memos(), [])
        self.assertEqual(len(self.s.memos(include_archived=True)), 1)

    def test_memo_order_pinned_then_recent(self):
        a = self.s.create_memo("a")
        b = self.s.create_memo("b")
        c = self.s.create_memo("c", pinned=True)
        self.assertEqual([m.id for m in self.s.memos()], [c, b, a])

    def test_memo_order_with_sent_draft(self):
        pinned = self.s.create_memo("p", pinned=True)
        old = self.s.create_memo("old")
        self.s.set_draft("  new one \n")
        sent = self.s.send_draft()
        self.assertEqual([m.id for m in self.s.memos()], [pinned, sent, old])

    def test_draft_round_trip(self):
        self.assertEqual(self.s.draft(), "")
        self.s.set_draft("first")
        self.s.set_draft(" second\n")
        self.assertEqual(self.s.draft(), " second\n")

    def test_send_draft_creates_trimmed_memo_and_clears(self):
        self.s.set_draft("\n  # hi\n- a  \n")
        mid = self.s.send_draft()
        self.assertEqual([(m.id, m.content) for m in self.s.memos()],
                         [(mid, "# hi\n- a")])
        self.assertEqual(self.s.draft(), "")

    def test_send_blank_draft_is_none(self):
        self.assertIsNone(self.s.send_draft())
        self.s.set_draft(" \n\t")
        self.assertIsNone(self.s.send_draft())
        self.assertEqual(self.s.memos(), [])
        self.assertEqual(self.s.draft(), " \n\t")

    def test_send_draft_is_atomic(self):
        self.s.set_draft("keep me")
        with mock.patch.object(Store, "create_memo", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.s.send_draft()
        self.assertEqual(self.s.draft(), "keep me")
        self.assertFalse(self.s._db.in_transaction)

    def test_memo_local_upsert_and_cascade(self):
        mid = self.s.create_memo("x")
        self.s.set_memo_local(mid, title="T")
        self.s.set_memo_local(mid, color="red")  # keeps title
        m = self.s.memos()[0]
        self.assertEqual((m.title, m.color), ("T", "red"))
        self.s.set_memo_local(mid, color=None)  # explicit None clears
        self.assertIsNone(self.s.memos()[0].color)
        self.s._db.execute("DELETE FROM memo WHERE id = ?", (mid,))
        count = self.s._db.execute("SELECT COUNT(*) FROM memo_local").fetchone()[0]
        self.assertEqual(count, 0)


class FileStoreTest(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "sub" / "t.db"

    def test_migration_version_and_idempotent_reopen(self):
        s = Store(self.path)
        self.assertEqual(s._db.execute("PRAGMA user_version").fetchone()[0], 2)
        s.add_clip("keep", 0)
        s.close()
        s = Store(self.path)
        self.addCleanup(s.close)
        self.assertEqual(s._db.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual([c.content for c in s.clips()], ["keep"])

    def test_v1_database_migrates_keeping_rows(self):
        self.path.parent.mkdir(parents=True)
        db = sqlite3.connect(self.path)
        db.executescript(store_mod._MIGRATIONS[0] + "PRAGMA user_version=1;")
        db.execute("INSERT INTO clip (content, content_hash, created_at, last_used_at)"
                   " VALUES ('c', 'h', 1, 1)")
        db.execute("INSERT INTO memo (id, content, create_time, update_time)"
                   " VALUES ('m', 'memo', 1, 1)")
        db.commit()
        db.close()
        s = Store(self.path)
        self.addCleanup(s.close)
        self.assertEqual(s._db.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual([c.content for c in s.clips()], ["c"])
        self.assertEqual([m.content for m in s.memos()], ["memo"])
        self.assertEqual(s.draft(), "")

    def test_wal_active(self):
        s = Store(self.path)
        self.addCleanup(s.close)
        self.assertEqual(s._db.execute("PRAGMA journal_mode").fetchone()[0], "wal")


if __name__ == "__main__":
    unittest.main()
