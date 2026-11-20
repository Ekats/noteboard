import QtQuick
import QtQuick.Controls
import QtQuick.Controls.impl
import QtQuick.Layouts

// Clipboard history on top, the latest sticky below. The popup aims the
// pointer at the middle of the first row, so it reads rowHeight to compute
// that spawn offset; the list must stay at the top of this page.
Item {
    // Every row is two text lines tall, one-liners included, so the list
    // reads as an even grid and two-line entries show whole.
    readonly property int twoLines: Math.ceil(fm.lineSpacing * 2)
    readonly property int rowHeight: twoLines + 12

    FontMetrics { id: fm }

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
                            id: label
                            Layout.fillWidth: true
                            Layout.alignment: row.expanded ? Qt.AlignTop : Qt.AlignVCenter
                            text: row.content.trim()
                            wrapMode: Text.Wrap
                            // Collapsed: two lines, with an ellipsis when
                            // more is hidden (extra lines or a long wrap).
                            maximumLineCount: row.expanded ? 100000 : 2
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

                        // Two lines tall like the row. Takes its own clicks,
                        // so expanding never pastes. Shown only when the
                        // collapsed text is actually cut off.
                        ToolButton {
                            Layout.alignment: Qt.AlignTop
                            Layout.preferredWidth: twoLines
                            Layout.preferredHeight: twoLines
                            padding: 0
                            visible: row.expanded || label.truncated
                            icon.name: row.expanded ? "arrow-up" : "arrow-down"
                            icon.width: twoLines - 6
                            icon.height: twoLines - 6
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
