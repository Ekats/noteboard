"""Qt list models over the store."""

from dataclasses import replace

from PySide6.QtCore import (Property, QAbstractListModel, QModelIndex, QObject, Qt,
                            Signal, Slot)

from noteboard.store import Store


class ClipModel(QAbstractListModel):
    ClipIdRole = Qt.ItemDataRole.UserRole + 1
    ContentRole = Qt.ItemDataRole.UserRole + 2
    PinnedRole = Qt.ItemDataRole.UserRole + 3

    limitChanged = Signal()

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self._store = store
        self._limit = 500
        self._clips = store.clips()

    def roleNames(self):
        return {
            self.ClipIdRole: b"clipId",
            self.ContentRole: b"content",
            self.PinnedRole: b"pinned",
        }

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._clips)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._clips):
            return None
        clip = self._clips[index.row()]
        if role == self.ClipIdRole:
            return clip.id
        if role == self.ContentRole:
            return clip.content
        if role == self.PinnedRole:
            return clip.pinned
        return None

    def _get_limit(self) -> int:
        return self._limit

    def _set_limit(self, value: int) -> None:
        if value == self._limit:
            return
        self._limit = value
        self._store.prune(value)
        self.reload()
        self.limitChanged.emit()

    limit = Property(int, _get_limit, _set_limit, notify=limitChanged)

    @Slot()
    def reload(self) -> None:
        self.beginResetModel()
        self._clips = self._store.clips()
        self.endResetModel()

    @Slot(str)
    def add(self, text: str) -> None:
        self._store.add_clip(text, self._limit)
        self.reload()

    @Slot(int, bool)
    def setPinned(self, clip_id: int, pinned: bool) -> None:
        self._store.set_clip_pinned(clip_id, pinned)
        self.reload()

    @Slot(int)
    def remove(self, clip_id: int) -> None:
        self._store.delete_clip(clip_id)
        self.reload()


class MemoModel(QAbstractListModel):
    MemoIdRole = Qt.ItemDataRole.UserRole + 1
    ContentRole = Qt.ItemDataRole.UserRole + 2
    PinnedRole = Qt.ItemDataRole.UserRole + 3
    UpdateTimeRole = Qt.ItemDataRole.UserRole + 4
    ColorRole = Qt.ItemDataRole.UserRole + 5

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self._store = store
        self._memos = store.memos()

    def roleNames(self):
        return {
            self.MemoIdRole: b"memoId",
            self.ContentRole: b"content",
            self.PinnedRole: b"pinned",
            self.UpdateTimeRole: b"updateTime",  # unix ms
            # Not "color": that would clash with the delegate's own property.
            self.ColorRole: b"noteColor",
        }

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._memos)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._memos):
            return None
        memo = self._memos[index.row()]
        if role == self.MemoIdRole:
            return memo.id
        if role == self.ContentRole:
            return memo.content
        if role == self.PinnedRole:
            return memo.pinned
        if role == self.UpdateTimeRole:
            return memo.update_time
        if role == self.ColorRole:
            return memo.color or ""
        return None

    @Slot(str, str)
    def setContent(self, memo_id: str, text: str) -> None:
        """Write an edit through without touching the list.

        No reset or reorder: the card is being edited under the cursor, and
        the view reloads once editing ends. The cached row is updated so a
        reload-free rebuild of the delegate still shows the new text.
        """
        for i, memo in enumerate(self._memos):
            if memo.id == memo_id:
                if memo.content != text:
                    self._store.update_memo(memo_id, content=text)
                    self._memos[i] = replace(memo, content=text)
                return

    @Slot()
    def reload(self) -> None:
        self.beginResetModel()
        self._memos = self._store.memos()
        self.endResetModel()


class Draft(QObject):
    """The capture pad's unsent text.

    Edits are written straight to the local store; only a future server push
    is meant to be debounced.
    """

    contentChanged = Signal()
    sent = Signal()

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self._store = store
        self._content = store.draft()

    def _get_content(self) -> str:
        return self._content

    content = Property(str, _get_content, notify=contentChanged)

    @Slot()
    def reload(self) -> None:
        content = self._store.draft()
        if content != self._content:
            self._content = content
            self.contentChanged.emit()

    @Slot(str)
    def setContent(self, text: str) -> None:
        # The text area reports reload()'s own update back through here;
        # comparing keeps that from writing (and from bumping update_time).
        # No contentChanged on a real edit: the view already shows the text.
        if text == self._content:
            return
        self._store.set_draft(text)
        self._content = text

    @Slot()
    def send(self) -> None:
        if self._store.send_draft() is None:
            return
        self._content = ""
        self.contentChanged.emit()
        self.sent.emit()
