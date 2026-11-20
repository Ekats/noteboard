import unittest
from unittest import mock

from noteboard import store as store_mod
from noteboard.models import ClipModel, MemoModel
from noteboard.store import Store


class ClipModelTest(unittest.TestCase):
    def setUp(self):
        ticks = iter(range(1000, 100000, 10))
        patcher = mock.patch.object(store_mod, "_now_ms", lambda: next(ticks))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.s = Store(":memory:")
        self.addCleanup(self.s.close)
        self.ids = [self.s.add_clip(c, 0) for c in "abcde"]  # newest first: e..a
        self.m = ClipModel(self.s)
        self.seen = []
        self.m.modelAboutToBeReset.connect(lambda: self.seen.append("reset"))
        self.m.rowsAboutToBeRemoved.connect(
            lambda _p, f, l: self.seen.append(("removed", f, l)))
        self.m.rowsAboutToBeInserted.connect(
            lambda _p, f, l: self.seen.append(("inserted", f, l)))
        self.m.rowsAboutToBeMoved.connect(
            lambda _p, f, _l, _d, r: self.seen.append(("moved", f, r)))

    def test_remove_drops_one_row_without_reset(self):
        self.m.remove(self.ids[2])  # "c", row 2
        self.assertEqual(self.seen, [("removed", 2, 2)])
        self.assertEqual(self.m._clips, self.s.clips())
        self.assertEqual(self.m.rowCount(), 4)

    def test_remove_pinned_clip(self):
        self.s.set_clip_pinned(self.ids[0], True)
        self.m.reload()
        self.seen.clear()
        self.m.remove(self.ids[0])
        self.assertEqual(self.seen, [("removed", 0, 0)])
        self.assertNotIn(self.ids[0], [c.id for c in self.m._clips])

    def test_reload_without_changes_emits_nothing(self):
        self.m.reload()
        self.assertEqual(self.seen, [])

    def test_pin_moves_row_without_reset(self):
        self.m.setPinned(self.ids[1], True)  # "b" jumps to the top
        self.assertEqual(self.seen, [("moved", 3, 0)])
        self.assertEqual(self.m._clips, self.s.clips())

    def test_recopy_moves_existing_row_to_top(self):
        self.m.add("a")
        self.assertNotIn("reset", self.seen)
        self.assertEqual(self.m._clips, self.s.clips())
        self.assertEqual(self.m._clips[0].content, "a")
        self.assertEqual(self.m.rowCount(), 5)

    def test_deleted_text_comes_back_as_new_entry(self):
        self.m.remove(self.ids[0])
        self.m.add("a")
        self.assertEqual([c.content for c in self.m._clips], ["a", "e", "d", "c", "b"])
        self.assertNotEqual(self.m._clips[0].id, self.ids[0])
        self.assertEqual(self.m._clips, self.s.clips())

    def test_limit_prune_matches_store(self):
        self.m.limit = 2
        self.assertEqual(self.m._clips, self.s.clips())
        self.assertEqual(self.m.rowCount(), 2)


class MemoModelTest(unittest.TestCase):
    def setUp(self):
        # Distinct times: equal ones tie-break on the random id.
        ticks = iter(range(1000, 100000, 10))
        patcher = mock.patch.object(store_mod, "_now_ms", lambda: next(ticks))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.s = Store(":memory:")
        self.addCleanup(self.s.close)
        self.a = self.s.create_memo("a")
        self.b = self.s.create_memo("b")
        self.s._db.execute("UPDATE memo SET dirty = 0")
        self.m = MemoModel(self.s)

    def contents(self):
        return [x.content for x in self.s.memos()]

    def test_set_pinned_moves_group_only_after_reload(self):
        self.m.setPinned(self.a, True)
        self.assertTrue(self.m._memos[1].pinned)  # cached, row not moved
        self.m.reload()
        self.assertEqual(self.m._memos[0].id, self.a)
        row = self.s._db.execute(
            "SELECT pinned, dirty FROM memo WHERE id = ?", (self.a,)).fetchone()
        self.assertEqual(tuple(row), (1, 1))
        self.m.setPinned(self.a, False)
        self.m.reload()
        self.assertEqual(self.contents(), ["b", "a"])

    def test_remove_tombstones_and_drops_row(self):
        self.m.remove(self.a)
        self.assertEqual(self.m.rowCount(), 1)
        row = self.s._db.execute(
            "SELECT deleted_at, dirty FROM memo WHERE id = ?", (self.a,)).fetchone()
        self.assertIsNotNone(row[0])
        self.assertEqual(row[1], 1)

    def watch(self):
        """Names of the structural signals the model emits, in order."""
        seen = []
        m = self.m
        m.modelAboutToBeReset.connect(lambda: seen.append("reset"))
        m.rowsRemoved.connect(lambda _p, a, b: seen.append(("removed", a, b)))
        m.rowsInserted.connect(lambda _p, a, b: seen.append(("inserted", a, b)))
        m.rowsMoved.connect(lambda _p, a, b, _d, to: seen.append(("moved", a, b, to)))
        m.dataChanged.connect(lambda i, _j, *_: seen.append(("changed", i.row())))
        return seen

    def test_reload_without_changes_emits_nothing(self):
        seen = self.watch()
        self.m.reload()
        self.assertEqual(seen, [])

    def test_reload_remove_is_incremental(self):
        c = self.s.create_memo("c")
        self.m.reload()
        seen = self.watch()
        self.s.delete_memo(self.a)
        self.m.reload()
        self.assertEqual(seen, [("removed", 2, 2)])
        self.assertEqual([x.id for x in self.m._memos], [c, self.b])

    def test_reload_pin_moves_row(self):
        self.s.update_memo(self.a, pinned=True, touch=False)
        seen = self.watch()
        self.m.reload()
        self.assertIn(("moved", 1, 1, 0), seen)
        self.assertNotIn("reset", seen)
        self.assertEqual([x.id for x in self.m._memos], [x.id for x in self.s.memos()])

    def test_reload_insert_and_edit(self):
        c = self.s.create_memo("c")
        self.s.update_memo(self.a, content="a2")  # a becomes newest
        seen = self.watch()
        self.m.reload()
        self.assertNotIn("reset", seen)
        self.assertEqual([x.id for x in self.m._memos], [x.id for x in self.s.memos()])
        self.assertEqual(self.m._memos[0].content, "a2")
        self.assertEqual(self.m.rowCount(), 3)
        self.assertEqual(c, next(x.id for x in self.m._memos if x.content == "c"))

    def test_reload_mixed_matches_store(self):
        ids = [self.s.create_memo(str(n)) for n in range(6)]
        self.m.reload()
        self.s.delete_memo(ids[1])
        self.s.delete_memo(ids[2])
        self.s.update_memo(ids[0], pinned=True, touch=False)
        self.s.update_memo(ids[4], content="x")
        new = self.s.create_memo("new")
        self.m.reload()
        self.assertEqual(self.m._memos, self.s.memos())
        self.assertIn(new, [x.id for x in self.m._memos])


if __name__ == "__main__":
    unittest.main()
