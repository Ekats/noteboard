"""Decides when to sync and runs sync() off the UI thread.

Nothing here touches the network or starts a thread until sync is enabled
and a server URL and token are set. The worker is the only place sync() runs,
on its own Store connection (WAL lets it write beside the UI's connection)."""

import sys
import threading
import time
import traceback

from PySide6.QtCore import Property, QObject, QThread, QTimer, Signal, Slot

from . import secrets
from .memos_client import MemosClient
from .store import Store
from .sync import SyncResult, sync

DEBOUNCE_MS = 3000          # after the last local memo write
STALE_S = 60                # popup show syncs if the last run is older
PERIODIC_MS = 10 * 60 * 1000
SHUTDOWN_WAIT_MS = 3000


class SyncWorker(QObject):
    """Lives on the worker thread; every slot below runs there, one at a
    time, so a token save can never overlap a run."""

    finished = Signal(object)           # SyncResult
    tokenResult = Signal(bool, bool, str)   # ok, token now set, error

    def __init__(self, db_path, *, sync_fn=sync, lookup_fn=secrets.lookup,
                 store_fn=secrets.store, clear_fn=secrets.clear):
        super().__init__()
        self._db_path = db_path
        self._sync = sync_fn
        self._lookup, self._store_token, self._clear = lookup_fn, store_fn, clear_fn
        self._stop = threading.Event()

    def stop(self) -> None:
        """Thread-safe: ends the current run between memos."""
        self._stop.set()

    @Slot(str)
    def run(self, url: str) -> None:
        if self._stop.is_set():
            self.finished.emit(SyncResult())
            return
        store = None
        try:
            token = self._lookup()
            if not token:
                res = SyncResult(errors=["No access token in the secret store"])
            else:
                # Opened per run: nothing long-lived to close on shutdown, and
                # sqlite connections must stay on the thread that made them.
                store = Store(self._db_path)
                res = self._sync(store, MemosClient(url, token),
                                 should_stop=self._stop.is_set)
        except Exception as e:  # keep the worker alive whatever goes wrong
            traceback.print_exc(file=sys.stderr)
            res = SyncResult(errors=[str(e) or type(e).__name__])
        finally:
            if store:
                store.close()
        self.finished.emit(res)

    @Slot(str)
    def saveToken(self, token: str) -> None:
        try:
            if token:
                self._store_token(token)
            else:
                self._clear()
        except secrets.SecretError as e:
            self.tokenResult.emit(False, False, str(e))
            return
        self.tokenResult.emit(True, bool(token), "")


def _summary(res: SyncResult) -> str:
    now = time.strftime("%H:%M")
    if res.errors:
        more = f" (+{len(res.errors) - 1} more)" if len(res.errors) > 1 else ""
        return f"Sync problem at {now}: {res.errors[0]}{more}"
    parts = [f"{n} {what}" for n, what in ((res.pushed, "sent"),
                                           (res.pulled, "received"),
                                           (res.deleted, "deleted"),
                                           (res.conflicts, "conflicts kept both"))
             if n]
    return f"Synced at {now}" + (": " + ", ".join(parts) if parts else "")


class SyncController(QObject):
    statusChanged = Signal()
    syncingChanged = Signal()
    enabledChanged = Signal()
    serverUrlChanged = Signal()
    tokenSetChanged = Signal()
    editingChanged = Signal()
    memosChanged = Signal()     # the store changed under the model: reload
    tokenStored = Signal(bool, bool, str)   # ok, token now set, error

    _runRequested = Signal(str)
    _saveRequested = Signal(str)

    def __init__(self, db_path, parent=None, *, worker_factory=None,
                 clock=time.monotonic, debounce_ms=DEBOUNCE_MS,
                 periodic_ms=PERIODIC_MS):
        super().__init__(parent)
        self._db_path = db_path
        self._worker_factory = worker_factory or (lambda: SyncWorker(db_path))
        self._clock = clock
        self._enabled = False
        self._url = ""
        self._token_set = False
        self._editing = False
        self._status = ""
        self._running = False
        self._again = False          # a trigger arrived mid-run: run once more
        self._reload_pending = False
        self._last_run = None        # clock() of the last finished run
        self._thread: QThread | None = None
        self._worker: SyncWorker | None = None
        self._active = False
        self.stuck = False           # set by shutdown(): worker did not stop in time

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)
        self._debounce.timeout.connect(self._request)
        self._periodic = QTimer(self)
        self._periodic.setInterval(periodic_ms)
        self._periodic.timeout.connect(self._request)

    # -- properties set from QML ---------------------------------------

    def _get_enabled(self): return self._enabled
    def _set_enabled(self, v: bool) -> None:
        if v != self._enabled:
            self._enabled = v
            self.enabledChanged.emit()
            self._refresh_active()
    enabled = Property(bool, _get_enabled, _set_enabled, notify=enabledChanged)

    def _get_url(self): return self._url
    def _set_url(self, v: str) -> None:
        v = v.strip()
        if v != self._url:
            self._url = v
            self.serverUrlChanged.emit()
            self._refresh_active(force_run=True)
    serverUrl = Property(str, _get_url, _set_url, notify=serverUrlChanged)

    def _get_token_set(self): return self._token_set
    def _set_token_set(self, v: bool) -> None:
        if v != self._token_set:
            self._token_set = v
            self.tokenSetChanged.emit()
            self._refresh_active()
    tokenSet = Property(bool, _get_token_set, _set_token_set, notify=tokenSetChanged)

    def _get_editing(self): return self._editing
    def _set_editing(self, v: bool) -> None:
        if v == self._editing:
            return
        self._editing = v
        self.editingChanged.emit()
        if not v and self._reload_pending:
            self._reload_pending = False
            self.memosChanged.emit()
    editing = Property(bool, _get_editing, _set_editing, notify=editingChanged)

    status = Property(str, lambda self: self._status, notify=statusChanged)
    syncing = Property(bool, lambda self: self._running, notify=syncingChanged)

    # -- triggers ------------------------------------------------------

    def _is_active(self) -> bool:
        return self._enabled and bool(self._url) and self._token_set

    def _refresh_active(self, force_run: bool = False) -> None:
        active = self._is_active()
        if not active:
            self._debounce.stop()
            self._periodic.stop()
            self._again = False
        elif not self._periodic.isActive():
            self._periodic.start()
        if active and (not self._active or force_run):
            self._request()     # startup, or newly configured
        self._active = active

    def changed(self) -> None:
        """A local memo was written (wired to Store.on_memo_change)."""
        if self._is_active():
            self._debounce.start()      # restart: wait for a pause in edits

    def popupShown(self) -> None:
        if self._is_active() and (self._last_run is None
                                  or self._clock() - self._last_run > STALE_S):
            self._request()

    @Slot()
    def syncNow(self) -> None:
        self._debounce.stop()
        self._request()

    def _request(self) -> None:
        """Every trigger funnels here; one run at a time, extra triggers
        coalesce into one follow-up run."""
        if not self._is_active():
            return
        if self._running:
            self._again = True
            return
        self._start_run()

    # -- worker --------------------------------------------------------

    def _ensure_worker(self) -> SyncWorker:
        if self._worker is None:
            self._thread = QThread()
            self._worker = self._worker_factory()
            self._worker.moveToThread(self._thread)
            self._runRequested.connect(self._worker.run)
            self._saveRequested.connect(self._worker.saveToken)
            self._worker.finished.connect(self._on_finished)
            self._worker.tokenResult.connect(self.tokenStored)
            self._thread.start()
        return self._worker

    def _start_run(self) -> None:
        self._ensure_worker()
        self._running = True
        self._again = False
        self.syncingChanged.emit()
        self._runRequested.emit(self._url)

    @Slot(object)
    def _on_finished(self, res: SyncResult) -> None:
        self._running = False
        self._last_run = self._clock()
        self.syncingChanged.emit()
        self._status = _summary(res)
        self.statusChanged.emit()
        if res.pushed or res.pulled or res.deleted or res.conflicts:
            if self._editing:
                # A reload reorders the list under the card being edited.
                self._reload_pending = True
            else:
                self.memosChanged.emit()
        if self._again and self._is_active():
            self._start_run()

    @Slot(str)
    def saveToken(self, token: str) -> None:
        """Empty clears it. Runs on the worker: the secret store can block."""
        self._ensure_worker()
        self._saveRequested.emit(token)

    def shutdown(self) -> None:
        """Let a running sync end between memos and wait briefly for it.

        If it is stuck in a network read, `stuck` is set and the caller must
        leave with os._exit: a QThread destructor on a running thread aborts,
        and terminate() could kill it while it holds the GIL. Abandoning the
        run is safe: the database is WAL, every sync write is its own
        transaction, and a half-finished push is reconciled by the next run."""
        self._debounce.stop()
        self._periodic.stop()
        self._again = False
        if self._thread is None:
            return
        self._worker.stop()
        self._thread.quit()
        self.stuck = not self._thread.wait(SHUTDOWN_WAIT_MS)
