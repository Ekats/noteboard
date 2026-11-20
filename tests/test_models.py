import unittest
from unittest import mock

from noteboard import store as store_mod
from noteboard.models import MemoModel
from noteboard.store import Store


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


if __name__ == "__main__":
    unittest.main()
