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

    def fail(self, state):
        self.keyboard.state = state
        self.keyboard.stateChanged.emit()

    def test_on_without_trusted_grant_switches_off_at_startup(self):
        self.grant(app_id="")  # token from before NoteBoard identified itself
        p = self.paster()
        self.assertTrue(p.autoPaste)
        p.begin()
        self.assertFalse(p.autoPaste)
        self.assertFalse(self.settings.value(AUTO_PASTE_KEY, type=bool))
        self.assertEqual(p.status, "off")
        self.assertNotIn("start", self.keyboard.calls)

    def test_on_without_any_token_switches_off_at_startup(self):
        self.settings.setValue(AUTO_PASTE_KEY, True)
        p = self.paster()
        p.begin()
        self.assertFalse(p.autoPaste)
        self.assertNotIn("start", self.keyboard.calls)

    def test_enabling_requests_immediately(self):
        p = self.paster()
        p.setAutoPaste(True)
        self.assertEqual(self.keyboard.calls, ["start"])
        self.assertEqual(p.status, "waiting")
        self.assertTrue(self.settings.value(AUTO_PASTE_KEY, type=bool))

    def test_decline_switches_off_and_persists(self):
        p = self.paster()
        p.setAutoPaste(True)
        self.fail("denied")
        self.assertFalse(p.autoPaste)
        self.assertFalse(self.settings.value(AUTO_PASTE_KEY, type=bool))
        self.assertEqual(p.status, "declined")
        p.paste("x")  # copy only
        self.assertEqual(self.clipboard.copied, ["x"])
        self.assertFalse(p._timeout.isActive())

    def test_enabling_again_clears_the_note(self):
        p = self.paster()
        p.setAutoPaste(True)
        self.fail("denied")
        p.setAutoPaste(True)
        self.assertEqual(p.status, "waiting")

    def test_no_portal_switches_off_with_note(self):
        p = self.paster()
        p.setAutoPaste(True)
        self.fail("unavailable")
        self.assertFalse(p.autoPaste)
        self.assertEqual(p.status, "unavailable")

    def test_startup_with_grant_starts_silently(self):
        self.grant()
        p = self.paster()
        p.begin()
        self.assertEqual(self.keyboard.calls, ["start"])
        self.assertTrue(p.autoPaste)

    def test_startup_grant_failing_switches_off(self):
        self.grant()
        p = self.paster()
        p.begin()
        self.fail("denied")
        self.assertFalse(p.autoPaste)
        self.assertFalse(self.settings.value(AUTO_PASTE_KEY, type=bool))

    def test_allowed_then_closed_switches_off(self):
        self.grant()
        p = self.paster()
        p.begin()
        self.keyboard.state = "allowed"
        self.keyboard.stateChanged.emit()
        self.assertEqual(p.status, "allowed")
        self.fail("denied")  # the portal's Closed signal
        self.assertFalse(p.autoPaste)
        self.assertEqual(p.status, "declined")

    def test_switching_off_closes_the_session(self):
        self.grant()
        p = self.paster()
        p.begin()
        p.setAutoPaste(False)
        self.assertEqual(self.keyboard.calls, ["start", "stop"])
        self.assertEqual(p.status, "off")


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
