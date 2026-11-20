import unittest
from unittest import mock

from noteboard import store as store_mod
from noteboard import sync as sync_mod
from noteboard.memos_client import (ApiError, AuthError, NetworkError,
                                    NotFoundError, RemoteMemo)
from noteboard.store import Store
from noteboard.sync import sync


class Clock:
    def __init__(self):
        self.t = 1000

    def __call__(self):
        self.t += 10
        return self.t


class FakeMemosServer:
    """In-memory stand-in with the MemosClient interface. Every write bumps
    update_time, like the real server."""

    def __init__(self, reject_memo_id=False):
        self.memos: dict[str, RemoteMemo] = {}
        self.attachments: dict[str, list] = {}
        self.reject_memo_id = reject_memo_id
        self.fail: dict[str, Exception] = {}   # memo id -> raised on create/update
        self.fail_update: dict[str, Exception] = {}  # memo id -> raised on update only
        self.list_error: Exception | None = None
        self.on_write = None                   # runs after a write, before the reply
        self.calls: list[tuple] = []
        self._t = 5_000_000
        self._n = 0

    def _tick(self) -> int:
        self._t += 1000
        return self._t

    def put(self, memo_id, content="r", *, pinned=False, state="NORMAL",
            visibility="PRIVATE", create_time=None) -> RemoteMemo:
        t = self._tick()
        m = RemoteMemo(memo_id, content, pinned, state, visibility,
                       create_time or t, t)
        self.memos[memo_id] = m
        return m

    def list_all(self):
        if self.list_error:
            raise self.list_error
        return list(self.memos.values())

    def create(self, fields, memo_id=None):
        self.calls.append(("create", memo_id, dict(fields)))
        if memo_id and self.reject_memo_id:
            raise ApiError("invalid memo id", 400)
        if memo_id is None:
            self._n += 1
            memo_id = f"srv{self._n}"
        if memo_id in self.fail:
            raise self.fail[memo_id]
        # Like the real server: state is ignored on create.
        m = self.put(memo_id, fields["content"], pinned=fields["pinned"],
                     state="NORMAL", visibility=fields["visibility"],
                     create_time=fields.get("create_time"))
        if self.on_write:
            self.on_write()
        return m

    def update(self, memo_id, fields):
        self.calls.append(("update", memo_id, dict(fields)))
        for table in (self.fail, self.fail_update):
            if memo_id in table:
                raise table[memo_id]
        if memo_id not in self.memos:
            raise NotFoundError("gone")
        old = self.memos[memo_id]
        m = self.put(memo_id, **{**{"content": old.content, "pinned": old.pinned,
                                    "state": old.state,
                                    "visibility": old.visibility,
                                    "create_time": old.create_time}, **fields})
        if self.on_write:
            self.on_write()
        return m

    def delete(self, memo_id):
        self.calls.append(("delete", memo_id))
        if self.memos.pop(memo_id, None) is None:
            raise NotFoundError("gone")

    def verbs(self, verb):
        return [c for c in self.calls if c[0] == verb]


class SyncTestBase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(store_mod, "_now_ms", Clock())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.s = Store(":memory:")
        self.addCleanup(self.s.close)
        self.srv = FakeMemosServer()

    def row(self, memo_id):
        return self.s._current(memo_id)

    def ids(self):
        return {r.id for r in self.s.sync_rows()}

    def pulled_clean(self, memo_id, content="r", **kw):
        """A memo that exists on both sides and is fully synced."""
        self.srv.put(memo_id, content, **kw)
        sync(self.s, self.srv)
        self.srv.calls.clear()
        return self.row(memo_id)

    def tombstone_clean(self, memo_id):
        """Tombstoned but not dirty: only reachable by hand, since
        delete_memo always marks dirty."""
        self.s.delete_memo(memo_id)
        self.s._db.execute("UPDATE memo SET dirty = 0 WHERE id = ?", (memo_id,))


class ReconcileRemoteSeen(SyncTestBase):
    def test_no_local_inserts_both_states(self):
        a = self.srv.put("a", "live")
        b = self.srv.put("b", "old", state="ARCHIVED", pinned=True)
        res = sync(self.s, self.srv)
        self.assertEqual((res.pulled, res.errors), (2, []))
        ra, rb = self.row("a"), self.row("b")
        self.assertEqual((ra.dirty, ra.synced_update_time, ra.update_time),
                         (False, a.update_time, a.update_time))
        self.assertEqual((rb.state, rb.pinned, rb.synced_update_time),
                         ("ARCHIVED", True, b.update_time))

    def test_tombstone_clean_applies_remote(self):
        self.pulled_clean("a", "one")
        self.tombstone_clean("a")
        self.srv.put("a", "two")
        sync(self.s, self.srv)
        r = self.row("a")
        self.assertEqual((r.content, r.deleted_at), ("two", None))
        self.assertEqual(self.srv.verbs("delete"), [])

    def test_tombstone_dirty_remote_changed_edit_beats_delete(self):
        self.pulled_clean("a", "one")
        self.s.delete_memo("a")
        self.srv.put("a", "edited elsewhere")
        res = sync(self.s, self.srv)
        r = self.row("a")
        self.assertEqual((r.content, r.deleted_at, r.dirty), ("edited elsewhere", None, False))
        self.assertEqual((res.pulled, res.deleted), (1, 0))
        self.assertEqual(self.srv.verbs("delete"), [])

    def test_tombstone_dirty_remote_unchanged_deletes_both(self):
        self.pulled_clean("a")
        self.s.delete_memo("a")
        res = sync(self.s, self.srv)
        self.assertNotIn("a", self.ids())
        self.assertNotIn("a", self.srv.memos)
        self.assertEqual(res.deleted, 1)

    def test_tombstone_dirty_edited_then_deleted_applies_remote(self):
        # Unchanged remote but local diverged before the delete: not equivalent.
        self.pulled_clean("a", "one")
        self.s.update_memo("a", content="local edit")
        self.s.delete_memo("a")
        sync(self.s, self.srv)
        self.assertEqual(self.row("a").content, "one")
        self.assertIsNone(self.row("a").deleted_at)

    def test_tombstone_delete_tolerates_already_gone(self):
        self.pulled_clean("a")
        self.s.delete_memo("a")
        real = self.srv.delete
        def racing_delete(i):           # server drops it between list and delete
            self.srv.memos.pop(i)
            return real(i)
        self.srv.delete = racing_delete
        res = sync(self.s, self.srv)
        self.assertEqual((res.errors, res.deleted), ([], 1))
        self.assertNotIn("a", self.ids())

    def test_equivalent_marks_synced_without_traffic(self):
        # Local dirty and never synced, but identical to what the server has
        # (e.g. a create whose reply was lost).
        self.s.create_memo("same")
        mid = next(iter(self.ids()))
        m = self.srv.put(mid, "same")
        res = sync(self.s, self.srv)
        r = self.row(mid)
        self.assertEqual((r.dirty, r.synced_update_time), (False, m.update_time))
        self.assertEqual((res.pushed, res.pulled, res.conflicts), (0, 0, 0))
        self.assertEqual(self.srv.calls, [])

    def test_local_clean_applies_remote_keeps_memo_local(self):
        self.pulled_clean("a", "one")
        self.s.set_memo_local("a", title="T", color="red", position=3)
        m = self.srv.put("a", "two", pinned=True, state="ARCHIVED", visibility="PUBLIC")
        res = sync(self.s, self.srv)
        r = self.row("a")
        self.assertEqual((r.content, r.pinned, r.state, r.visibility, r.update_time,
                          r.synced_update_time, r.dirty),
                         ("two", True, "ARCHIVED", "PUBLIC", m.update_time,
                          m.update_time, False))
        self.assertEqual(res.pulled, 1)
        mem = next(x for x in self.s.memos(include_archived=True) if x.id == "a")
        self.assertEqual((mem.title, mem.color, mem.position), ("T", "red", 3))

    def test_dirty_remote_unchanged_pushes_patch_without_attachments(self):
        self.pulled_clean("a", "one")
        self.srv.attachments["a"] = ["file.png"]
        self.s.update_memo("a", content="two", pinned=True)
        res = sync(self.s, self.srv)
        (verb, mid, fields), = self.srv.verbs("update")
        self.assertEqual((verb, mid), ("update", "a"))
        self.assertEqual(set(fields), {"content", "pinned", "state", "visibility"})
        self.assertEqual(self.srv.memos["a"].content, "two")
        self.assertEqual(self.srv.attachments["a"], ["file.png"])
        r = self.row("a")
        self.assertEqual((r.dirty, r.synced_update_time),
                         (False, self.srv.memos["a"].update_time))
        self.assertEqual(res.pushed, 1)

    def test_both_changed_keeps_both(self):
        self.pulled_clean("a", "base")
        self.s.set_memo_local("a", title="T", color="blue", reminder_at=99, position=7)
        self.s.update_memo("a", content="local")
        self.srv.put("a", "remote")
        res = sync(self.s, self.srv)
        self.assertEqual((res.conflicts, res.pushed, res.errors), (1, 1, []))
        self.assertEqual(self.row("a").content, "remote")
        self.assertFalse(self.row("a").dirty)
        (new_id,) = self.ids() - {"a"}
        self.assertNotEqual(new_id, "a")
        self.assertEqual(self.row(new_id).content, "local")
        self.assertEqual(self.srv.memos[new_id].content, "local")
        self.assertFalse(self.row(new_id).dirty)
        self.assertEqual({m.content for m in self.srv.memos.values()}, {"remote", "local"})
        mem = {m.id: m for m in self.s.memos()}
        for i in ("a", new_id):         # memo_local follows the copy, stays on the original
            self.assertEqual((mem[i].title, mem[i].color, mem[i].reminder_at,
                              mem[i].position), ("T", "blue", 99, 7))

    def test_never_synced_dirty_with_different_remote_is_conflict(self):
        self.s.create_memo("mine")
        mid = next(iter(self.ids()))
        self.srv.put(mid, "theirs")
        res = sync(self.s, self.srv)
        self.assertEqual(res.conflicts, 1)
        self.assertEqual(self.row(mid).content, "theirs")


class ReconcileMissingFromServer(SyncTestBase):
    def test_synced_tombstoned_hard_deletes(self):
        self.pulled_clean("a")
        self.s.delete_memo("a")
        del self.srv.memos["a"]
        res = sync(self.s, self.srv)
        self.assertNotIn("a", self.ids())
        self.assertEqual((res.deleted, self.srv.calls), (1, []))

    def test_synced_dirty_recreated_with_same_id(self):
        self.pulled_clean("a", "one")
        self.s.update_memo("a", content="edited")
        del self.srv.memos["a"]
        res = sync(self.s, self.srv)
        self.assertEqual(self.srv.calls[0][:2], ("create", "a"))
        self.assertEqual(self.srv.memos["a"].content, "edited")
        self.assertFalse(self.row("a").dirty)
        self.assertEqual(res.pushed, 1)

    def test_synced_clean_hard_deletes_server_deleted(self):
        self.pulled_clean("a")
        del self.srv.memos["a"]
        res = sync(self.s, self.srv)
        self.assertNotIn("a", self.ids())
        self.assertEqual((res.deleted, self.srv.calls), (1, []))

    def test_never_synced_tombstoned_hard_deletes_locally(self):
        mid = self.s.create_memo("x")
        self.s.delete_memo(mid)
        res = sync(self.s, self.srv)
        self.assertEqual((self.ids(), res.deleted, self.srv.calls), (set(), 1, []))

    def test_never_synced_created_with_memo_id(self):
        mid = self.s.create_memo("new", pinned=True)
        res = sync(self.s, self.srv)
        (verb, used_id, fields), = self.srv.calls
        self.assertEqual((verb, used_id), ("create", mid))
        self.assertEqual((fields["content"], fields["pinned"]), ("new", True))
        self.assertEqual(len(mid), 32)
        r = self.row(mid)
        self.assertEqual((r.dirty, r.synced_update_time),
                         (False, self.srv.memos[mid].update_time))
        self.assertEqual(res.pushed, 1)
        sync(self.s, self.srv)          # second run is a no-op
        self.assertEqual(len(self.srv.calls), 1)


class ArchivedCreate(SyncTestBase):
    def test_archived_local_memo_is_archived_after_create(self):
        mid = self.s.create_memo("old")
        self.s.update_memo(mid, state="ARCHIVED")
        res = sync(self.s, self.srv)
        self.assertEqual(res.errors, [])
        self.assertEqual(self.srv.memos[mid].state, "ARCHIVED")
        r = self.row(mid)
        self.assertEqual((r.state, r.dirty, r.synced_update_time),
                         ("ARCHIVED", False, self.srv.memos[mid].update_time))

    def test_archive_step_failing_retries_instead_of_duplicating(self):
        mid = self.s.create_memo("old")
        self.s.update_memo(mid, state="ARCHIVED")
        self.srv.fail_update[mid] = ApiError("boom", 500)
        res = sync(self.s, self.srv)
        self.assertEqual(len(res.errors), 1)
        r = self.row(mid)
        self.assertEqual((r.state, r.dirty), ("ARCHIVED", True))
        self.assertEqual(r.synced_update_time, self.srv.memos[mid].update_time)
        self.srv.fail_update.clear()
        res = sync(self.s, self.srv)
        self.assertEqual((res.conflicts, res.errors), (0, []))
        self.assertEqual(self.ids(), {mid})
        self.assertEqual(self.srv.memos[mid].state, "ARCHIVED")
        self.assertFalse(self.row(mid).dirty)


class MemoIdRejected(SyncTestBase):
    def test_rejected_memo_id_moves_row_and_memo_local(self):
        self.srv.reject_memo_id = True
        mid = self.s.create_memo("new")
        self.s.set_memo_local(mid, title="T", color="green", position=2)
        res = sync(self.s, self.srv)
        self.assertEqual(res.errors, [])
        self.assertEqual(self.ids(), {"srv1"})
        r = self.row("srv1")
        self.assertEqual((r.content, r.dirty, r.synced_update_time),
                         ("new", False, self.srv.memos["srv1"].update_time))
        (mem,) = self.s.memos()
        self.assertEqual((mem.id, mem.title, mem.color, mem.position),
                         ("srv1", "T", "green", 2))
        orphans = self.s._db.execute(
            "SELECT count(*) FROM memo_local WHERE memo_id = ?", (mid,)).fetchone()[0]
        self.assertEqual(orphans, 0)

    def test_non_400_create_error_is_not_retried_without_id(self):
        mid = self.s.create_memo("new")
        self.srv.fail[mid] = ApiError("boom", 500)
        res = sync(self.s, self.srv)
        self.assertEqual(len(self.srv.verbs("create")), 1)
        self.assertEqual(len(res.errors), 1)


class EditDuringPush(SyncTestBase):
    def test_edit_during_update_keeps_local_and_stays_dirty(self):
        self.pulled_clean("a", "one")
        self.s.update_memo("a", content="pushed")
        self.srv.on_write = lambda: self.s.update_memo("a", content="typed meanwhile")
        sync(self.s, self.srv)
        r = self.row("a")
        self.assertEqual((r.content, r.dirty), ("typed meanwhile", True))
        self.assertEqual(r.synced_update_time, self.srv.memos["a"].update_time)
        self.srv.on_write = None
        sync(self.s, self.srv)          # next run pushes the newer text
        self.assertEqual(self.srv.memos["a"].content, "typed meanwhile")
        self.assertFalse(self.row("a").dirty)

    def test_edit_during_create_keeps_local_and_stays_dirty(self):
        mid = self.s.create_memo("first")
        self.srv.on_write = lambda: self.s.update_memo(mid, content="second")
        sync(self.s, self.srv)
        r = self.row(mid)
        self.assertEqual((r.content, r.dirty), ("second", True))
        self.assertEqual(r.synced_update_time, self.srv.memos[mid].update_time)
        self.srv.on_write = None
        sync(self.s, self.srv)
        self.assertEqual(self.srv.memos[mid].content, "second")
        self.assertFalse(self.row(mid).dirty)

    def test_edit_during_create_with_moved_id_follows_server_id(self):
        self.srv.reject_memo_id = True
        mid = self.s.create_memo("first")
        self.s.set_memo_local(mid, title="T")
        self.srv.on_write = lambda: self.s.update_memo(mid, content="second")
        sync(self.s, self.srv)
        # The callback edits the old id, which no longer exists after the move
        # only if the edit lands after it; here it lands before finish_push.
        r = self.row("srv1")
        self.assertEqual((r.content, r.dirty), ("second", True))
        self.assertEqual(self.s.memos()[0].title, "T")

    def test_edit_between_snapshot_and_write_is_not_overwritten(self):
        # Pull path: the guarded write must notice the row changed after the
        # snapshot (here: while the server listing is in flight).
        self.pulled_clean("a", "one")
        self.srv.put("a", "remote")
        real = self.srv.list_all
        def list_then_edit():
            out = real()
            self.s.update_memo("a", content="typed")
            return out
        self.srv.list_all = list_then_edit
        # Snapshot is taken after list_all, so take it earlier by wrapping rows.
        snapshot = self.s.sync_rows()
        with mock.patch.object(self.s, "sync_rows", return_value=snapshot):
            sync(self.s, self.srv)
        r = self.row("a")
        self.assertEqual((r.content, r.dirty), ("typed", True))


class Robustness(SyncTestBase):
    def test_one_failing_memo_does_not_abort_the_rest(self):
        bad = self.s.create_memo("bad")
        good = self.s.create_memo("good")
        self.srv.put("r", "remote")
        self.srv.fail[bad] = ApiError("boom", 500)
        res = sync(self.s, self.srv)
        self.assertEqual(len(res.errors), 1)
        self.assertIn(bad, res.errors[0])
        self.assertIn(good, self.srv.memos)
        self.assertIn("r", self.ids())
        self.assertTrue(self.row(bad).dirty)
        self.srv.fail.clear()           # retried next run
        sync(self.s, self.srv)
        self.assertFalse(self.row(bad).dirty)

    def test_failed_listing_changes_nothing(self):
        self.pulled_clean("a")
        self.s.update_memo("a", content="edited")
        self.srv.list_error = NetworkError("down")
        res = sync(self.s, self.srv)
        self.assertEqual(len(res.errors), 1)
        self.assertIn("down", res.errors[0])
        self.assertEqual((self.row("a").content, self.row("a").dirty), ("edited", True))
        self.assertEqual(self.srv.calls, [])

    def test_auth_error_stops_the_run(self):
        a, b = self.s.create_memo("a"), self.s.create_memo("b")
        self.srv.fail[a] = self.srv.fail[b] = AuthError("bad token")
        res = sync(self.s, self.srv)
        self.assertEqual(len(res.errors), 1)
        self.assertEqual(len(self.srv.verbs("create")), 1)

    def test_draft_never_synced(self):
        self.s.set_draft("unsent thoughts")
        self.s.create_memo("m")
        sync(self.s, self.srv)
        self.assertEqual(self.s.draft(), "unsent thoughts")
        self.assertNotIn("unsent thoughts", [m.content for m in self.srv.memos.values()])

    def test_idempotent_second_run(self):
        self.s.create_memo("m")
        self.srv.put("r")
        sync(self.s, self.srv)
        self.srv.calls.clear()
        res = sync(self.s, self.srv)
        self.assertEqual((res.pushed, res.pulled, res.conflicts, res.deleted,
                          res.errors, self.srv.calls), (0, 0, 0, 0, [], []))


if __name__ == "__main__":
    unittest.main()
