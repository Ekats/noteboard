"""Two-way sync of the memo table with a Memos server. No Qt, no threads: the
caller runs sync() wherever it likes. The rules follow the MoeMemos apps'
SyncingRepository: equality on the server's updateTime decides "remote
changed", an edit beats a delete, and a true conflict keeps both versions."""

import sqlite3
from dataclasses import dataclass, field

from .memos_client import (ApiError, AuthError, MemosError, NetworkError,
                           NotFoundError, RemoteMemo)
from .store import Store, SyncRow


@dataclass
class SyncResult:
    pushed: int = 0
    pulled: int = 0
    conflicts: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)


def _equivalent(local: SyncRow, remote: RemoteMemo) -> bool:
    return (local.content == remote.content and local.pinned == remote.pinned
            and local.visibility == remote.visibility
            and local.state == remote.state)


def _remote_changed(local: SyncRow, remote: RemoteMemo) -> bool:
    # Never synced (None) counts as changed.
    return local.synced_update_time != remote.update_time


def _patch_fields(row: SyncRow) -> dict:
    # No attachments/relations here, and the mask is derived from these keys,
    # so whatever the server holds besides these fields survives.
    return {"content": row.content, "pinned": row.pinned, "state": row.state,
            "visibility": row.visibility}


def _push_new(store: Store, client, row: SyncRow, res: SyncResult) -> None:
    fields = {**_patch_fields(row), "create_time": row.create_time}
    try:
        remote = client.create(fields, memo_id=row.id)
    except ApiError as e:
        if e.status != 400:
            raise
        # Server refuses client-chosen ids: let it pick, finish_push moves
        # the row (and its memo_local) to that id.
        remote = client.create(fields)
    if remote.state != row.state:
        # The server creates everything as NORMAL, so archive in a second call.
        try:
            remote = client.update(remote.id, {"state": row.state})
        except MemosError:
            # The memo exists remotely now: record the linkage but keep the
            # local row dirty so the next run retries instead of duplicating.
            store.finish_push(row, remote, keep_local=True)
            raise
    store.finish_push(row, remote)
    res.pushed += 1


def _push_update(store: Store, client, row: SyncRow, res: SyncResult) -> None:
    store.finish_push(row, client.update(row.id, _patch_fields(row)))
    res.pushed += 1


def _delete_both(store: Store, client, row: SyncRow, res: SyncResult) -> None:
    try:
        client.delete(row.id)
    except NotFoundError:
        pass  # already gone: same outcome
    if store.hard_delete(row):
        res.deleted += 1


def _pull(store: Store, row: SyncRow, remote: RemoteMemo, res: SyncResult) -> None:
    if store.apply_remote(row, remote):
        res.pulled += 1


def _reconcile(store: Store, client, res: SyncResult,
               local: SyncRow | None, remote: RemoteMemo) -> None:
    if local is None:
        if store.insert_remote(remote):
            res.pulled += 1
    elif local.deleted_at is not None:
        if not local.dirty:
            _pull(store, local, remote, res)
        elif _remote_changed(local, remote) or not _equivalent(local, remote):
            _pull(store, local, remote, res)  # an edit beats a delete
        else:
            _delete_both(store, client, local, res)
    elif _equivalent(local, remote):
        store.mark_synced(local, remote)
    elif not local.dirty:
        _pull(store, local, remote, res)
    elif not _remote_changed(local, remote):
        _push_update(store, client, local, res)
    else:
        dup = store.duplicate_as_new(local, remote)
        if dup is not None:
            res.conflicts += 1
            res.pulled += 1
            _push_new(store, client, dup, res)


def _reconcile_missing(store: Store, client, res: SyncResult, row: SyncRow) -> None:
    """Local row the server did not list."""
    if row.synced_update_time is not None:
        # Known to the server before, so it was deleted there; a dirty edit
        # is worth more than that delete and is re-created under the same id.
        if row.deleted_at is None and row.dirty:
            _push_new(store, client, row, res)
        elif store.hard_delete(row):
            res.deleted += 1
    elif row.deleted_at is not None:
        if store.hard_delete(row):  # never reached the server
            res.deleted += 1
    else:
        _push_new(store, client, row, res)


def sync(store: Store, client, should_stop=None) -> SyncResult:
    """should_stop is polled between memos so a quitting app can end the run
    early; whatever was not reached is simply picked up next time."""
    res = SyncResult()
    try:
        remote = client.list_all()
    except MemosError as e:
        # Never reconcile against a failed listing: it would read as "the
        # server deleted everything".
        res.errors.append(f"Could not list memos: {e}")
        return res
    local = {r.id: r for r in store.sync_rows()}
    seen = {r.id for r in remote}
    steps = [(r.id, lambda r=r: _reconcile(store, client, res, local.get(r.id), r))
             for r in remote]
    steps += [(row.id, lambda row=row: _reconcile_missing(store, client, res, row))
              for row in local.values() if row.id not in seen]
    for memo_id, step in steps:
        if should_stop and should_stop():
            break
        try:
            step()
        except (AuthError, NetworkError) as e:
            # Every further call would fail the same way.
            res.errors.append(f"Sync stopped: {e}")
            break
        except (MemosError, sqlite3.Error) as e:
            res.errors.append(f"Memo {memo_id}: {e}")
    return res
