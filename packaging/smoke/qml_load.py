"""Load the installed Popup.qml on the offscreen platform.

Run against an installed package (not the source tree) to prove its QML
imports all resolve, including org.kde.layershell. The context properties are
the real models over a throw-away database, as in noteboard/__main__.py, minus
the parts that touch the session (the wl-paste watcher is never started and
the portal is never contacted).

Exits 0 when the window loaded and Qt reported no missing module or type.
"""

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
tmp = tempfile.mkdtemp(prefix="noteboard-smoke-")
# QSettings and the store must not touch a real profile.
os.environ["XDG_CONFIG_HOME"] = tmp + "/config"
os.environ["XDG_DATA_HOME"] = tmp + "/data"

from PySide6.QtCore import QTimer, qInstallMessageHandler  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

import noteboard  # noqa: E402
from noteboard.clipboard import WaylandClipboard  # noqa: E402
from noteboard.models import ClipModel, Draft, MemoModel  # noqa: E402
from noteboard.paste import Paster, PortalKeyboard  # noqa: E402
from noteboard.store import Store  # noqa: E402
from noteboard.syncctl import SyncController  # noqa: E402
from noteboard.textformat import LineHeight  # noqa: E402

BAD = re.compile(r"is not installed|is not a type|unavailable|"
                 r"No such file or directory|Cannot load library|"
                 r"ReferenceError|Cannot assign|Type .* unavailable")
messages: list[str] = []


def handler(_mode, _ctx, msg):
    messages.append(msg)
    print("qt:", msg, file=sys.stderr)


qInstallMessageHandler(handler)

app = QGuiApplication(sys.argv)
app.setApplicationName("noteboard")
app.setOrganizationName("noteboard")

db = Path(tmp) / "noteboard.db"
store = Store(db)
clip_model = ClipModel(store)
draft = Draft(store)
memo_model = MemoModel(store)
sync_ctl = SyncController(db)
paster = Paster(WaylandClipboard(), PortalKeyboard())

engine = QQmlApplicationEngine()
ctx = engine.rootContext()
ctx.setContextProperty("blockFormat", LineHeight())
ctx.setContextProperty("clipModel", clip_model)
ctx.setContextProperty("paster", paster)
ctx.setContextProperty("draft", draft)
ctx.setContextProperty("memoModel", memo_model)
ctx.setContextProperty("syncController", sync_ctl)

qml = Path(noteboard.__file__).parent / "qml" / "Popup.qml"
print("loading", qml)
engine.load(qml)
roots = engine.rootObjects()
if not roots:
    print("FAIL: Popup.qml produced no root object", file=sys.stderr)
    sys.exit(1)

# Show it and let a few frames render so deferred (Loader/Behavior) bindings run.
roots[0].setVisible(True)
QTimer.singleShot(1500, app.quit)
app.exec()

bad = [m for m in messages if BAD.search(m)]
if bad:
    print("FAIL: QML reported problems:", *bad, sep="\n  ", file=sys.stderr)
    sys.exit(1)
print("OK: Popup.qml loaded on the offscreen platform")
