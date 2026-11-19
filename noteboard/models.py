"""Qt list models over the store."""

from PySide6.QtCore import (Property, QAbstractListModel, QModelIndex, Qt,
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
