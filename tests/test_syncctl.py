import threading
import time
import unittest

from PySide6.QtCore import QCoreApplication

from noteboard.store import Store
from noteboard.sync import SyncResult
from noteboard.syncctl import SyncController, SyncWorker

app = QCoreApplication.instance() or QCoreApplication([])


def wait_until(pred, timeout=3.0):
    end = time.monotonic() + timeout
    while not pred():
        if time.monotonic() > end:
            raise AssertionError("timed out")
        app.processEvents()
        time.sleep(0.005)


def settle(ms=150):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


class Env:
    """A controller whose worker runs a scripted sync_fn."""

    def __init__(self, sync_fn=None, clock=time.monotonic, token="tok"):
        self.runs = []
        self.saved = []

        def default(store, client, should_stop=None):
            return SyncResult()

        self.sync_fn = sync_fn or default
        self.token = token
        self.ctl = SyncController(
            ":memory:", clock=clock, debounce_ms=40, periodic_ms=10_000,
            worker_factory=lambda: SyncWorker(
                ":memory:", sync_fn=self._sync, lookup_fn=lambda: self.token,
                store_fn=self.saved.append, clear_fn=lambda: self.saved.append("")))

    def _sync(self, store, client, should_stop=None):
        self.runs.append(client._base)
        return self.sync_fn(store, client, should_stop)

    def configure(self):
        self.ctl.serverUrl = "http://memos.test"
        self.ctl.tokenSet = True
        self.ctl.enabled = True


class SyncControllerTest(unittest.TestCase):
    def make(self, **kw):
        env = Env(**kw)
        self.addCleanup(env.ctl.shutdown)
        return env

    def test_off_until_enabled_url_and_token(self):
        env = self.make()
        env.ctl.enabled = True
        env.ctl.serverUrl = "http://memos.test"      # still no token
        env.ctl.changed()
        env.ctl.popupShown()
        env.ctl.syncNow()
        settle(150)
        self.assertIsNone(env.ctl._thread)
        self.assertEqual(env.runs, [])
        self.assertFalse(env.ctl._debounce.isActive() or env.ctl._periodic.isActive())

    def test_disabling_stops_triggers(self):
        env = self.make()
        env.configure()
        wait_until(lambda: len(env.runs) == 1)
        env.ctl.enabled = False
        env.ctl.changed()
        env.ctl.popupShown()
        settle(150)
        self.assertEqual(len(env.runs), 1)
        self.assertFalse(env.ctl._periodic.isActive())

    def test_configuring_runs_once_at_startup(self):
        env = self.make()
        env.configure()
        wait_until(lambda: env.ctl.status.startswith("Synced"))
        settle(100)
        self.assertEqual(env.runs, ["http://memos.test"])

    def test_missing_token_reports_instead_of_syncing(self):
        env = self.make(token=None)
        env.configure()
        wait_until(lambda: env.ctl.status != "")
        self.assertIn("token", env.ctl.status)
        self.assertEqual(env.runs, [])

    def test_local_changes_are_debounced_into_one_run(self):
        env = self.make()
        env.configure()
        wait_until(lambda: len(env.runs) == 1)
        for _ in range(5):
            env.ctl.changed()
            settle(10)
        wait_until(lambda: len(env.runs) == 2)
        settle(150)
        self.assertEqual(len(env.runs), 2)

    def test_triggers_during_a_run_coalesce_into_one_more(self):
        release = threading.Event()

        def slow(store, client, should_stop):
            release.wait(3)
            return SyncResult()

        env = self.make(sync_fn=slow)
        env.configure()
        wait_until(lambda: env.ctl.syncing)
        for _ in range(4):
            env.ctl.syncNow()
        release.set()
        wait_until(lambda: len(env.runs) == 2 and not env.ctl.syncing)
        settle(150)
        self.assertEqual(len(env.runs), 2)

    def test_popup_show_syncs_only_when_stale(self):
        now = [1000.0]
        env = self.make(clock=lambda: now[0])
        env.configure()
        wait_until(lambda: len(env.runs) == 1 and not env.ctl.syncing)
        now[0] += 30
        env.ctl.popupShown()
        settle(100)
        self.assertEqual(len(env.runs), 1)
        now[0] += 31
        env.ctl.popupShown()
        wait_until(lambda: len(env.runs) == 2)

    def test_reload_after_changes_but_not_after_a_quiet_run(self):
        results = [SyncResult(), SyncResult(pulled=2)]
        env = self.make(sync_fn=lambda *a: results.pop(0))
        reloads = []
        env.ctl.memosChanged.connect(lambda: reloads.append(1))
        env.configure()
        wait_until(lambda: not results[1:] and not env.ctl.syncing)
        settle(50)
        self.assertEqual(reloads, [])
        env.ctl.syncNow()
        wait_until(lambda: reloads)

    def test_reload_deferred_while_editing(self):
        env = self.make(sync_fn=lambda *a: SyncResult(pulled=1))
        reloads = []
        env.ctl.memosChanged.connect(lambda: reloads.append(1))
        env.ctl.editing = True
        env.configure()
        wait_until(lambda: env.ctl.status.startswith("Synced"))
        settle(100)
        self.assertEqual(reloads, [])
        env.ctl.editing = False
        self.assertEqual(reloads, [1])

    def test_shutdown_stops_a_running_sync_promptly(self):
        started = threading.Event()

        def loop(store, client, should_stop):
            started.set()
            while not should_stop():
                time.sleep(0.01)
            return SyncResult()

        env = Env(sync_fn=loop)
        env.configure()
        wait_until(started.is_set)
        t0 = time.monotonic()
        env.ctl.shutdown()
        self.assertLess(time.monotonic() - t0, 1.5)
        self.assertFalse(env.ctl._thread.isRunning())

    def test_shutdown_reports_a_sync_stuck_in_the_network(self):
        started, release = threading.Event(), threading.Event()

        def stuck(store, client, should_stop):
            started.set()
            release.wait(30)    # ignores should_stop, like a blocked read
            return SyncResult()

        env = Env(sync_fn=stuck)
        from noteboard import syncctl
        old, syncctl.SHUTDOWN_WAIT_MS = syncctl.SHUTDOWN_WAIT_MS, 200
        self.addCleanup(setattr, syncctl, "SHUTDOWN_WAIT_MS", old)
        env.configure()
        wait_until(started.is_set)
        env.ctl.shutdown()
        # Never terminate(): the caller leaves via os._exit instead.
        self.assertTrue(env.ctl.stuck)
        self.assertTrue(env.ctl._thread.isRunning())
        release.set()
        self.assertTrue(env.ctl._thread.wait(2000))     # let the QThread die cleanly

    def test_idle_shutdown_is_not_stuck(self):
        env = self.make()
        env.configure()
        wait_until(lambda: len(env.runs) == 1 and not env.ctl.syncing)
        env.ctl.shutdown()
        self.assertFalse(env.ctl.stuck)

    def test_token_save_and_clear_go_through_the_worker(self):
        env = self.make()
        got = []
        env.ctl.tokenStored.connect(lambda *a: got.append(a))
        env.ctl.saveToken("secret")
        wait_until(lambda: len(got) == 1)
        env.ctl.saveToken("")
        wait_until(lambda: len(got) == 2)
        self.assertEqual(env.saved, ["secret", ""])
        self.assertEqual(got, [(True, True, ""), (True, False, "")])
        self.assertEqual(env.runs, [])      # saving a token never syncs by itself


class StoreChangeHookTest(unittest.TestCase):
    def test_local_writes_notify_but_sync_writes_do_not(self):
        s = Store(":memory:")
        self.addCleanup(s.close)
        calls = []
        s.on_memo_change = lambda: calls.append(1)
        s.set_draft("hi")
        self.assertEqual(calls, [])             # draft is never synced
        s.send_draft()
        self.assertEqual(len(calls), 1)
        mid = s.memos()[0].id
        s.update_memo(mid, content="x")
        s.delete_memo(mid)
        self.assertEqual(len(calls), 3)
        s.set_memo_local(mid, color="red")      # local-only field
        row = s.sync_rows()[0]
        from noteboard.memos_client import RemoteMemo
        s.apply_remote(row, RemoteMemo(mid, "r", False, "NORMAL", "PRIVATE", 1, 2))
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
