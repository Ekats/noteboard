"""Clipboard capture and copy-back through wl-clipboard.

A Wayland client only sees the selection while it has focus, so the daemon
cannot watch the clipboard itself. wl-paste can: it speaks the data-control
protocol, which KWin offers to any client.
"""

import sys
import time

from PySide6.QtCore import QCoreApplication, QObject, QProcess, QTimer, Signal, Slot

# Emits the content only for CLIPBOARD_STATE=data. wl-paste sets
# "sensitive" when the offer carries x-kde-passwordManagerHint (password
# managers), and nil/clear for an empty clipboard; none of those may be
# stored. The NUL ends the frame because clipboard text can span lines.
WATCH_COMMAND = '[ "$CLIPBOARD_STATE" = data ] && { cat; printf "\\0"; }; true'

BACKOFF_FIRST_S = 1
BACKOFF_MAX_S = 30
# A watcher that lived this long was healthy, so its next failure starts
# the backoff over.
HEALTHY_RUN_S = 10


class NulFramer:
    """Splits a byte stream into NUL-terminated text frames."""

    def __init__(self):
        self._buf = b""

    def feed(self, data: bytes) -> list[str]:
        self._buf += data
        *frames, self._buf = self._buf.split(b"\0")
        # Decoding whole frames only: NUL never occurs inside a multibyte
        # UTF-8 sequence, so a character split across chunks is rejoined.
        return [f.decode("utf-8", errors="replace") for f in frames]


class WaylandClipboard(QObject):
    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._framer = NulFramer()
        self._backoff_s = BACKOFF_FIRST_S
        self._started_at = 0.0
        self._stopping = False
        self._copiers: set[QProcess] = set()

        self._watcher = QProcess(self)
        self._watcher.readyReadStandardOutput.connect(self._on_output)
        self._watcher.finished.connect(self._on_finished)
        self._watcher.errorOccurred.connect(self._on_error)
        self._restart = QTimer(self, singleShot=True)
        self._restart.timeout.connect(self._start)

        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop)

    def start(self) -> None:
        self._start()

    def _start(self) -> None:
        self._framer = NulFramer()  # drop any half frame from a dead watcher
        self._started_at = time.monotonic()
        # --type text: an offer with no text type (an image) starts nothing.
        self._watcher.start("wl-paste", ["--type", "text", "--watch",
                                         "sh", "-c", WATCH_COMMAND])

    def _stop(self) -> None:
        self._stopping = True
        self._restart.stop()
        self._watcher.kill()

    def _on_output(self) -> None:
        data = bytes(self._watcher.readAllStandardOutput().data())
        for text in self._framer.feed(data):
            if text:
                self.changed.emit(text)

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            print("noteboard: wl-paste not found, clipboard capture is off "
                  "(install wl-clipboard)", file=sys.stderr)
            self._stopping = True  # not a crash, so no restart loop

    def _on_finished(self) -> None:
        if self._stopping:
            return
        if time.monotonic() - self._started_at >= HEALTHY_RUN_S:
            self._backoff_s = BACKOFF_FIRST_S
        self._restart.start(self._backoff_s * 1000)
        self._backoff_s = min(self._backoff_s * 2, BACKOFF_MAX_S)

    @Slot(str)
    def copy(self, text: str) -> None:
        # wl-copy forks and keeps serving the selection itself. The change
        # is then captured like any other, and the store's dedupe moves the
        # entry to the top -- that is intended.
        proc = QProcess(self)
        self._copiers.add(proc)
        proc.finished.connect(lambda *_: self._copiers.discard(proc))
        proc.finished.connect(proc.deleteLater)
        proc.errorOccurred.connect(
            lambda err: print(f"noteboard: wl-copy failed: {err}", file=sys.stderr))
        # --type: skip wl-copy's xdg-mime guess, which would need to come
        # out as text for the watcher to see the copy at all.
        proc.start("wl-copy", ["--type", "text/plain;charset=utf-8"])
        proc.write(text.encode("utf-8"))
        proc.closeWriteChannel()
