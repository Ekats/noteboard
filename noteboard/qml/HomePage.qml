import QtQuick
import QtQuick.Controls
import QtQuick.Controls.impl
import QtQuick.Layouts

// Clipboard history. The popup aims the pointer at the middle of the first
// row, so it reads rowHeight to compute that spawn offset.
Item {
    readonly property int rowHeight: 32

    ListView {
        id: list
        anchors.fill: parent
        clip: true
        model: clipModel

        delegate: ItemDelegate {
            required property string content
            required property bool pinned

            width: ListView.view.width
            height: rowHeight
            // Clicking does nothing yet; copy-back arrives with clipboard capture.

            contentItem: RowLayout {
                spacing: 6

                Label {
                    Layout.fillWidth: true
                    // First line only; the rest would just wrap the row.
                    text: content.split("\n")[0].trim()
                    elide: Text.ElideRight
                }

                IconImage {
                    visible: pinned
                    name: "pin"
                    color: palette.windowText
                    sourceSize.width: 16
                    sourceSize.height: 16
                }
            }
        }
    }

    Label {
        anchors.centerIn: parent
        visible: list.count === 0
        text: qsTr("No clipboard history yet")
        color: palette.placeholderText
    }
}
