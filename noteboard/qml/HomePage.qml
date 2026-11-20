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
                    id: row
                    required property string content
                    required property bool pinned

                    // A trailing newline alone does not make an entry multi-line.
                    readonly property bool multiLine: content.trim().indexOf("\n") !== -1
                    // Not persisted: delegates are rebuilt on every show, so
                    // the popup always opens collapsed and the first row stays
                    // rowHeight tall where the pointer lands.
                    property bool expanded: false

                    width: ListView.view.width
                    height: expanded
                        ? Math.max(rowHeight, implicitContentHeight + topPadding + bottomPadding)
                        : rowHeight
                    onClicked: {
                        paster.paste(content);
                        picked();
                    }

                    contentItem: RowLayout {
                        spacing: 6

                        Label {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignTop
                            // Collapsed shows the first line only, with an
                            // ellipsis when more lines are hidden.
                            text: row.expanded ? row.content.trim()
                                : row.content.trim().split("\n")[0] + (row.multiLine ? " …" : "")
                            wrapMode: row.expanded ? Text.Wrap : Text.NoWrap
                            elide: Text.ElideRight
                        }

                        IconImage {
                            Layout.alignment: Qt.AlignTop
                            visible: row.pinned
                            name: "pin"
                            color: palette.windowText
                            sourceSize.width: 16
                            sourceSize.height: 16
                        }

                        // Takes its own clicks, so expanding never pastes.
                        ToolButton {
                            Layout.alignment: Qt.AlignTop
                            Layout.preferredWidth: 20
                            Layout.preferredHeight: 20
                            padding: 0
                            visible: row.multiLine
                            icon.name: row.expanded ? "arrow-up" : "arrow-down"
                            icon.width: 16
                            icon.height: 16
                            onClicked: row.expanded = !row.expanded
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
