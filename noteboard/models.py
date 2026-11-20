"""Qt list models over the store."""

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


class LatestMemo(QObject):
    """The most recently edited sticky, as one editable text.

    Edits are written straight to the local store; only a future server push
    is meant to be debounced.
    """

    memoIdChanged = Signal()
    contentChanged = Signal()

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self._store = store
        self._memo_id = ""
        self._content = ""
        self.reload()

    def _get_memo_id(self) -> str:
        return self._memo_id

    def _get_content(self) -> str:
        return self._content

    memoId = Property(str, _get_memo_id, notify=memoIdChanged)
    content = Property(str, _get_content, notify=contentChanged)

    @Slot()
    def reload(self) -> None:
        memo = self._store.latest_memo()
        memo_id, content = (memo.id, memo.content) if memo else ("", "")
        if memo_id != self._memo_id:
            self._memo_id = memo_id
            self.memoIdChanged.emit()
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
        if self._memo_id:
            self._store.update_memo(self._memo_id, content=text)
        elif text.strip():
            self._memo_id = self._store.create_memo(text)
            self.memoIdChanged.emit()
        else:
            return
        self._content = text
