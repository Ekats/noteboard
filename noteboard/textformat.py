"""Text formatting QML cannot reach on its own."""

from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QTextBlockFormat, QTextCursor
from PySide6.QtQuick import QQuickTextDocument

PROPORTIONAL = QTextBlockFormat.LineHeightTypes.ProportionalHeight


class LineHeight(QObject):
    """Keeps a proportional line height on every block of a text document.

    TextEdit has no lineHeight property, only the block format has it. Hooking
    contentsChange covers load, paste, clear and typing alike: setText resets
    the formats, while a block split off by Enter inherits its parent's.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._held = []

    @Slot(QQuickTextDocument, float)
    def keep(self, quick_doc: QQuickTextDocument, factor: float) -> None:
        # The QTextDocument wrapper is a child of this one and is invalidated
        # when QML's temporary argument wrapper dies, so hold that wrapper and
        # fetch the document through it on every change.
        self._held.append(quick_doc)
        percent = round(factor * 100)
        busy = False

        def apply(pos: int, removed: int, added: int) -> None:
            nonlocal busy
            if busy:  # our own format change reports back as a content change
                return
            busy = True
            try:
                doc = quick_doc.textDocument()
                # An empty stack means a load rather than an edit; see below.
                fresh = doc.availableUndoSteps() == 0
                cursor = QTextCursor(doc)
                # Joined to the edit that triggered it, so undo does not stop
                # on a format-only step.
                cursor.joinPreviousEditBlock()
                block = doc.findBlock(pos)
                end = pos + added
                while block.isValid() and block.position() <= end:
                    fmt = block.blockFormat()
                    if fmt.lineHeightType() != PROPORTIONAL.value or fmt.lineHeight() != percent:
                        fmt.setLineHeight(percent, PROPORTIONAL.value)
                        cursor.setPosition(block.position())
                        cursor.setBlockFormat(fmt)
                    block = block.next()
                cursor.endEditBlock()
                if fresh:
                    # Loading text is not something Ctrl+Z should step back
                    # through, least of all as a format-only step.
                    doc.setUndoRedoEnabled(False)
                    doc.setUndoRedoEnabled(True)
            finally:
                busy = False

        quick_doc.textDocument().contentsChange.connect(apply)
        apply(0, 0, max(0, quick_doc.textDocument().characterCount() - 1))
