import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QSettings, Signal

from noteboard.paste import (APP_ID, AUTO_PASTE_KEY, TOKEN_APP_KEY, TOKEN_KEY,
                             Paster, PortalKeyboard, has_grant,
                             migrate_auto_paste)

app = QCoreApplication.instance() or QCoreApplication([])


class FakeClipboard(QObject):
    changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.copied = []

    def copy(self, text):
        self.copied.append(text)


class FakeKeyboard(QObject):
    """Stands in for the portal: no D-Bus, only the calls Paster makes."""
    stateChanged = Signal()

    def __init__(self):
        super().__init__()
        self.state = "off"
        self.calls = []

    def start(self):
        self.calls.append("start")
        self.state = "waiting"
        self.stateChanged.emit()

    def stop(self):
        self.calls.append("stop")
        self.state = "off"
        self.stateChanged.emit()

    def send_combo(self, keys):
        self.calls.append(("combo", keys))
        return True


class PasteSettingsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.dir.name) / "t.ini"),
                                  QSettings.Format.IniFormat)
        self.clipboard = FakeClipboard()
        self.keyboard = FakeKeyboard()

    def tearDown(self):
        self.dir.cleanup()

    def paster(self):
        return Paster(self.clipboard, self.keyboard, settings=self.settings)

    def grant(self, app_id=APP_ID):
        self.settings.setValue(TOKEN_KEY, "tok")
        self.settings.setValue(TOKEN_APP_KEY, app_id)

    def test_fresh_install_defaults_off(self):
        self.assertFalse(migrate_auto_paste(self.settings))
        self.assertEqual(self.settings.value(AUTO_PASTE_KEY, type=bool), False)

    def test_existing_token_defaults_on(self):
        self.settings.setValue(TOKEN_KEY, "tok")  # granted before the app id
        self.assertTrue(migrate_auto_paste(self.settings))

    def test_migration_runs_once(self):
        self.settings.setValue(AUTO_PASTE_KEY, False)
        self.settings.setValue(TOKEN_KEY, "tok")
        self.assertFalse(migrate_auto_paste(self.settings))

    def test_grant_needs_own_app_id(self):
        self.grant(app_id="")
        self.assertFalse(has_grant(self.settings))
        self.grant()
        self.assertTrue(has_grant(self.settings))

    def test_off_creates_no_session_and_only_copies(self):
        p = self.paster()
        p.begin()
        p.paste("hello")
        self.clipboard.changed.emit("hello")
        app.processEvents()
        self.assertEqual(self.clipboard.copied, ["hello"])
        self.assertEqual(self.keyboard.calls, [])
        self.assertEqual(p.status, "off")

    def test_on_with_grant_starts_at_begin(self):
        self.grant()
        p = self.paster()
        p.begin()
        self.assertEqual(self.keyboard.calls, ["start"])

    def test_migrated_on_with_old_identity_waits_for_consent(self):
        self.grant(app_id="")
        p = self.paster()
        self.assertTrue(p.autoPaste)
        p.begin()
        self.assertEqual(self.keyboard.calls, [])
        self.assertEqual(p.status, "consent")
        p.confirmConsent()
        self.assertEqual(self.keyboard.calls, ["start"])
        self.assertEqual(p.status, "waiting")

    def test_switching_on_without_grant_asks_for_consent_first(self):
        p = self.paster()
        p.setAutoPaste(True)
        self.assertEqual(p.status, "consent")
        self.assertEqual(self.keyboard.calls, [])

    def test_cancel_switches_off(self):
        p = self.paster()
        p.setAutoPaste(True)
        p.setAutoPaste(False)
        self.assertEqual(p.status, "off")
        self.assertFalse(self.settings.value(AUTO_PASTE_KEY, type=bool))

    def test_switching_off_closes_the_session(self):
        self.grant()
        p = self.paster()
        p.begin()
        p.setAutoPaste(False)
        self.assertEqual(self.keyboard.calls, ["start", "stop"])

    def test_switching_on_with_grant_starts_without_consent(self):
        self.grant()
        self.settings.setValue(AUTO_PASTE_KEY, False)
        p = self.paster()
        p.setAutoPaste(True)
        self.assertEqual(self.keyboard.calls, ["start"])


class PortalKeyboardOffTest(unittest.TestCase):
    def test_stop_without_a_session_touches_no_portal(self):
        with tempfile.TemporaryDirectory() as d:
            kb = PortalKeyboard(settings=QSettings(
                str(Path(d) / "t.ini"), QSettings.Format.IniFormat))
            kb.stop()
            self.assertEqual(kb.state, "off")
            self.assertFalse(kb.ready)
            self.assertIsNone(kb._conn)


if __name__ == "__main__":
    unittest.main()
