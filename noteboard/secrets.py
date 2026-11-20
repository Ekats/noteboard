"""The Memos access token, kept in the Secret Service (KWallet / GNOME
Keyring) through libsecret, never in noteboard.conf.

These calls are synchronous and can block on D-Bus (even on an unlock
prompt), so they must only run on the sync worker thread."""

import os

import gi

gi.require_version("Secret", "1")
from gi.repository import Secret  # noqa: E402

# Overridable so a live test can use a throwaway entry instead of the real one.
_SERVICE = os.environ.get("NOTEBOARD_SECRET_SERVICE", "memos-token")

_SCHEMA = Secret.Schema.new(
    "io.github.ekats.noteboard", Secret.SchemaFlags.NONE,
    {"service": Secret.SchemaAttributeType.STRING})


class SecretError(Exception):
    pass


def _call(fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # GLib.Error: no keyring, locked and dismissed, ...
        raise SecretError(f"Secret store unavailable: {e}") from None


def lookup() -> str | None:
    return _call(Secret.password_lookup_sync, _SCHEMA, {"service": _SERVICE}, None)


def store(token: str) -> None:
    _call(Secret.password_store_sync, _SCHEMA, {"service": _SERVICE},
          Secret.COLLECTION_DEFAULT, f"NoteBoard {_SERVICE}", token, None)


def clear() -> None:
    _call(Secret.password_clear_sync, _SCHEMA, {"service": _SERVICE}, None)
