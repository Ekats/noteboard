# Sync

## Notes on sync

The local store mirrors the [Memos](https://github.com/usememos/memos) v1
data model — Markdown content, inline `#tags`, `pinned`, `state` — because
Memos has a documented, versioned API. Fields Memos has no room for
(note colour, title, reminders) are kept local-only and never sync.

## Syncing with a Memos server

Targets Memos 0.30. Off until you open Settings → Memos sync, switch it on,
enter the server URL and paste an access token (create one in Memos under
Settings → My account → Access tokens). The token is kept in the Secret
Service (KWallet / GNOME Keyring) via libsecret — needs `python3-gobject`
and `libsecret` — and never written to `noteboard.conf`. Until all three are
set, no thread is started and nothing touches the network.

Syncing runs on a worker thread at startup, 3 s after a local memo change,
when the popup opens if the last run is over a minute old, every 10 minutes
and on **Sync now**; overlapping triggers coalesce into one run. The note list
reloads when a run changed something, after you finish editing a card if one
is open. A reload updates the list row by row (remove, insert, move) rather
than resetting it, so the scroll position survives deletes, pins, edits and
sync runs.

Rules, ported from the MoeMemos apps:

- Memos are matched by id (local notes are created with a 32-char hex id,
  which the server accepts). "Changed on the server" means its `updateTime`
  differs from the one recorded at the last sync (the server only has
  second resolution).
- Edited only here → pushed (only content, pinned, state and visibility, so
  attachments on the server are left alone). Edited only on the server →
  pulled. Edited on both → both are kept: your version becomes a new note,
  the server's replaces the original.
- Deleting here deletes on the server; deleting on the server deletes here —
  unless you edited it here meanwhile, in which case it is re-created. An
  edit made elsewhere beats a delete made here.
- Edits made while a push is in flight are never overwritten; they go out
  on the next run.
- Colour, title, reminders and the capture-pad draft stay local.
- Only your own memos are synced, archived ones included.

## Google Keep

Google Keep has no official API for personal accounts
(`keep.googleapis.com` is Workspace enterprise-only), so Keep is a one-way
importer rather than a sync peer. The importer is not written yet.
