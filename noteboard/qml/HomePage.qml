import QtQuick
import QtQuick.Controls
import QtQuick.Controls.impl
import QtQuick.Layouts

// Clipboard history on top, the latest sticky below. The popup aims the
// pointer at the middle of the first row, so it reads rowHeight to compute
// that spawn offset; the list must stay at the top of this page.
Item {
    readonly property int rowHeight: 32

    // Emitted after a row is pasted; the window decides to close.
    signal picked()

    ColumnLayout {
        anchors.fill: parent
        spacing: 4

        // Both halves share a preferredHeight so the layout splits the page
        // evenly between them.
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: 1

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
                    onClicked: {
                        paster.paste(content);
                        picked();
                    }

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

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: palette.mid
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: 1

            TextArea {
                id: note
                wrapMode: TextArea.Wrap
                placeholderText: qsTr("Write a note…")
                text: latestMemo.content
                // Written through on every edit. A reload that changes the
                // text comes back here too, but setContent ignores a value
                // that already matches the memo.
                onTextChanged: latestMemo.setContent(text)
            }
        }
    }
}
