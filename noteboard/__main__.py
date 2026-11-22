"""Entry point for the noteboard popup daemon.

QT_WAYLAND_SHELL_INTEGRATION has to be set before Qt opens the Wayland
connection, so it happens here rather than in a wrapper script. Note that it
applies to every window in the process, which is why the notes board will be
a separate process -- see the README.
"""

import os
import signal
import socket
import sys
from pathlib import Path

os.environ.setdefault("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell")

from PySide6.QtCore import QSocketNotifier, QStandardPaths, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication, QRegion  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

from noteboard.clipboard import WaylandClipboard  # noqa: E402
from noteboard.kwin import KWinScript  # noqa: E402
from noteboard.shortcut import ShortcutClaim  # noqa: E402
from noteboard.models import ClipModel, Draft, MemoModel # noqa: E402
from noteboard.paste import Paster, PortalKeyboard  # noqa: E402
from noteboard.service import PopupService  # noqa: E402
from noteboard.store import Store  # noqa: E402
from noteboard.syncctl import SyncController  # noqa: E402
from noteboard.textformat import LineHeight  # noqa: E402
from noteboard.tray import Tray  # noqa: E402

QML_DIR = Path(__file__).parent / "qml"

# Used only if the QML has not laid out yet and cannot report where its
# first list row sits.
FALLBACK_ROW_OFFSET = 64


def _quit_on_signals(app) -> QSocketNotifier:
    """SIGTERM (systemctl stop) and SIGINT take the normal quit path.

    Python only runs signal handlers when the interpreter executes bytecode,
    which a sleeping Qt loop never does. The wakeup fd makes the C-level
    handler write to a socket the loop watches, and the notifier's slot is
    Python, so the real handler runs right after."""
    rsock, wsock = socket.socketpair()
    rsock.setblocking(False)
    wsock.setblocking(False)
    signal.set_wakeup_fd(wsock.fileno())
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: app.quit())
    notifier = QSocketNotifier(rsock.fileno(), QSocketNotifier.Type.Read)
    notifier.activated.connect(lambda: rsock.recv(64))
    notifier.sockets = (rsock, wsock)   # keep the sockets as long as the notifier
    return notifier


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("noteboard")
    app.setOrganizationName("noteboard")  # where QtCore Settings persists to
    app.setDesktopFileName("io.github.ekats.noteboard")

    # AppDataLocation would double-nest (noteboard/noteboard) because the
    # organisation and application names are the same.
    data_dir = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericDataLocation)) / "noteboard"
    store = Store(data_dir / "noteboard.db")
    clip_model = ClipModel(store)  # referenced here so it is not collected
    draft = Draft(store)
    memo_model = MemoModel(store)
    draft.sent.connect(memo_model.reload)

    # Idle (no thread, no network) until enabled and configured in Settings.
    sync_ctl = SyncController(data_dir / "noteboard.db")
    store.on_memo_change = sync_ctl.changed
    sync_ctl.memosChanged.connect(memo_model.reload)
    app.aboutToQuit.connect(sync_ctl.shutdown)

    clipboard = WaylandClipboard()
    clipboard.changed.connect(clip_model.add)

    keyboard = PortalKeyboard()
    paster = Paster(clipboard, keyboard)

    line_height = LineHeight()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("blockFormat", line_height)
    engine.rootContext().setContextProperty("clipModel", clip_model)
    engine.rootContext().setContextProperty("paster", paster)
    engine.rootContext().setContextProperty("draft", draft)
    engine.rootContext().setContextProperty("memoModel", memo_model)
    engine.rootContext().setContextProperty("syncController", sync_ctl)
    engine.load(QML_DIR / "Popup.qml")
    roots = engine.rootObjects()
    if not roots:
        return 1
    window = roots[0]

    def place(x: int, y: int, screen_name: str, window_class: str,
              page: str) -> None:
        """Show the popup near (x, y) on the named output.

        x and y arrive output-relative from the KWin script. Clamping keeps
        the popup fully on that output when the pointer is near an edge.
        """
        screen = next((s for s in app.screens() if s.name() == screen_name), None)
        if screen is not None:
            # A layer surface is bound to an output when it is created, so a
            # live surface cannot be moved between outputs -- it has to be
            # destroyed and recreated. QWindow.screen() is no help in
            # deciding when: it does not track the output the layer surface
            # actually went to, and reports the primary screen regardless.
            # Since the popup is hidden between shows, just recreate every
            # time. setVisible(False) would not do it either, as Qt collapses
            # a hide/show pair in one event loop pass.
            window.destroy()
            window.setScreen(screen)
            window.setProperty("targetScreen", screen)

        paster.set_target(window_class)
        window.setProperty("page", 1 if page == "notes" else 0)

        # The window is the panel plus a transparent margin for the shadow.
        # Aim the pointer at the first list row rather than at the panel's
        # corner: centred horizontally, and far enough down that the newest
        # clipboard entry opens directly under the cursor.
        margin = window.property("shadowMargin")
        panel_w = window.property("panelWidth")
        panel_h = window.property("panelHeight")
        row_offset = window.property("firstRowOffset") or FALLBACK_ROW_OFFSET
        x -= window.width() // 2
        y -= row_offset

        # Only the panel is kept on the output; the margin may hang off it.
        if screen is not None:
            bounds = screen.geometry()
            x = min(x, bounds.width() - panel_w - margin)
            y = min(y, bounds.height() - panel_h - margin)
        window.setProperty("originX", max(-margin, x))
        window.setProperty("originY", max(-margin, y))
        # No cross-process change notification yet, so pick up rows written
        # by other processes (the board) on every show.
        clip_model.reload()
        draft.reload()
        memo_model.reload()
        sync_ctl.popupShown()
        window.setVisible(True)
        # Clicks in the shadow margin fall through to the windows below.
        window.setMask(QRegion(margin, margin, panel_w, panel_h))
        window.requestActivate()

    service = PopupService()
    service.showRequested.connect(place)
    if not service.register():
        print("noteboard: could not take the D-Bus name, is it already running?",
              file=sys.stderr)
        return 1

    # After registering, so the shortcut never fires at a daemon that is not
    # listening yet.
    kwin_script = KWinScript()  # referenced here so it is not collected
    claim = ShortcutClaim()  # referenced here so it is not collected
    # Delayed so KWin has registered the script's shortcuts by then.
    kwin_script.loaded.connect(lambda: QTimer.singleShot(1000, claim.claim))
    kwin_script.ensure()
    tray = Tray(window)  # referenced here so it is not collected
    clipboard.start()
    paster.begin()

    signal_wakeup = _quit_on_signals(app)  # referenced here so it is not collected
    rc = app.exec()
    if sync_ctl.stuck:
        # The sync worker is blocked in a network read and a running QThread
        # cannot be destroyed, so skip interpreter teardown. Close what needs
        # it first; exit code stays 0 so Restart=on-failure leaves a Quit quit.
        store.close()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
