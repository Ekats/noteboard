import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "sticky.js" as Sticky

// Sent notes as sticky cards in one column. The Keep-style masonry belongs
// to the board window, not this popup.
Item {
    // Point size for the card text; set from the font setting.
    property real fontSize: 12
    // Bold and italic come from the font root in Popup.qml.
    property bool fontOutline: false
    // Default card colour, from the sticky colour setting.
    property string stickyColor: "#af9659"
    // Card background alpha in percent; the text stays opaque.
    property int innerOpacity: 90

    // The memo whose card is open for editing; empty = none. One at a time.
    property string editingId: ""
    readonly property bool editing: editingId !== ""
    // Edits are written through as they happen, but the list is only
    // reloaded once editing ends: a reload reorders by update time and would
    // yank the card from under the cursor.
    property bool edited: false

    function startEdit(id) {
        editingId = id;
    }

    function finishEdit() {
        if (!editing) return;
        editingId = "";
        if (edited) {
            edited = false;
            memoModel.reload();
        }
    }

    // A tap anywhere but the editing card (or any card's edit button, which
    // handles itself) ends the edit; the card cannot know, as taps outside
    // it never reach it.
    TapHandler {
        onTapped: eventPoint => {
            if (!editing) return;
            const x = eventPoint.position.x + list.contentX;
            const y = eventPoint.position.y + list.contentY;
            const hit = list.itemAt(x, y);
            if (hit && (hit.memoId === editingId
                    || hit.onEditButton(x - hit.x, y - hit.y))) return;
            finishEdit();
        }
    }

    ListView {
        id: list
        anchors.fill: parent
        clip: true
        spacing: 6
        model: memoModel

        delegate: Rectangle {
            id: card
            required property string memoId
            required property string content
            required property double updateTime
            required property string noteColor  // empty: follow the default

            // A per-note colour wins; otherwise the setting applies.
            readonly property string fill: noteColor !== "" ? noteColor : stickyColor
            readonly property bool editing: memoId === editingId

            function onEditButton(px, py) {
                return px >= editButton.x && px < editButton.x + editButton.width
                    && py >= editButton.y && py < editButton.y + editButton.height;
            }

            width: ListView.view.width
            height: (editing ? editor.height : body.implicitHeight)
                + stamp.implicitHeight + 8 + 20
            radius: 8
            color: Qt.alpha(fill, innerOpacity / 100)

            HoverHandler { id: cardHover }

            OutlineLabel {
                id: body
                visible: !card.editing
                outline: fontOutline
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 10
                anchors.bottomMargin: 0
                color: Sticky.ink(card.fill)
                linkColor: Sticky.isLight(card.fill) ? "#14357a" : "#9ec1ff"
                font.pointSize: fontSize
                lineHeight: Sticky.lineFactor
                textFormat: Text.MarkdownText
                wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                text: Sticky.breakLines(card.content)
            }

            // Raw Markdown, set like the draft pad. Loaded only while editing
            // so idle cards stay cheap.
            Loader {
                id: editor
                active: card.editing
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 10
                anchors.bottomMargin: 0
                height: item ? item.implicitHeight : 0
                sourceComponent: TextArea {
                    wrapMode: TextArea.Wrap
                    // The style sets the sides individually, which beats a
                    // plain padding: 0 and would shift the text off the label's spot.
                    leftPadding: 0
                    rightPadding: 0
                    topPadding: 0
                    bottomPadding: 0
                    font.pointSize: fontSize
                    color: Sticky.ink(card.fill)
                    selectByMouse: true
                    background: null
                    text: card.content
                    // Not on the initial text, which is not an edit. Compared
                    // against the model, not card.content: that stays at the
                    // opening text, so typing back to it must still be saved.
                    property bool ready: false
                    Component.onCompleted: {
                        blockFormat.keep(textDocument, Sticky.lineFactor);
                        forceActiveFocus();
                        cursorPosition = length;
                        ready = true;
                    }
                    onTextChanged: {
                        if (!ready) return;
                        memoModel.setContent(card.memoId, text);
                        edited = true;
                    }
                    Keys.onPressed: event => {
                        if (event.key === Qt.Key_Escape
                                || ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                                    && (event.modifiers & Qt.ControlModifier))) {
                            finishEdit();
                            event.accepted = true;
                        }
                    }
                }
            }

            ToolButton {
                id: editButton
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: 2
                width: 28
                height: 28
                padding: 0
                visible: cardHover.hovered || card.editing
                icon.name: card.editing ? "dialog-ok-apply" : "document-edit"
                icon.width: 16
                icon.height: 16
                icon.color: Sticky.ink(card.fill)
                onClicked: card.editing ? finishEdit() : startEdit(card.memoId)
                ToolTip.visible: hovered
                ToolTip.text: card.editing ? qsTr("Done") : qsTr("Edit")
            }

            OutlineLabel {
                id: stamp
                outline: fontOutline
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                anchors.margins: 10
                color: Sticky.muted(card.fill)
                font.pointSize: Math.max(8, fontSize - 3)
                text: new Date(card.updateTime).toLocaleString(Qt.locale(), Locale.ShortFormat)
            }
        }
    }

    OutlineLabel {
        outline: fontOutline
        anchors.centerIn: parent
        visible: list.count === 0
        text: qsTr("No notes yet — send one from Capture")
        color: palette.placeholderText
    }
}
