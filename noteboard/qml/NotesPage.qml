import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "sticky.js" as Sticky

// Sent notes as sticky cards in one column. The Keep-style masonry belongs
// to the board window, not this popup.
Item {
    // Point size for the card text; set from the font setting.
    property real fontSize: 12
    // Default card colour, from the sticky colour setting.
    property string stickyColor: "#af9659"

    ListView {
        id: list
        anchors.fill: parent
        clip: true
        spacing: 6
        model: memoModel

        delegate: Rectangle {
            id: card
            required property string content
            required property double updateTime
            required property string noteColor  // empty: follow the default

            // A per-note colour wins; otherwise the setting applies.
            readonly property string fill: noteColor !== "" ? noteColor : stickyColor

            width: ListView.view.width
            height: body.implicitHeight + stamp.implicitHeight + 8 + 20
            radius: 8
            color: fill

            Label {
                id: body
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 10
                anchors.bottomMargin: 0
                color: Sticky.ink(card.fill)
                linkColor: Sticky.isLight(card.fill) ? "#14357a" : "#9ec1ff"
                font.pointSize: fontSize
                textFormat: Text.MarkdownText
                wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                text: Sticky.breakLines(card.content)
            }

            Label {
                id: stamp
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                anchors.margins: 10
                color: Sticky.muted(card.fill)
                font.pointSize: Math.max(8, fontSize - 3)
                text: new Date(card.updateTime).toLocaleString(Qt.locale(), Locale.ShortFormat)
            }
        }
    }

    Label {
        anchors.centerIn: parent
        visible: list.count === 0
        text: qsTr("No notes yet — send one from Capture")
        color: palette.placeholderText
    }
}
