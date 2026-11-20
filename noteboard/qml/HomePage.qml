import QtQuick
import QtQuick.Controls
import QtQuick.Controls.impl
import QtQuick.Effects
import QtQuick.Layouts
import "sticky.js" as Sticky

// Clipboard history on top, the latest sticky below. The popup aims the
// pointer at the middle of the first row, so it reads rowHeight to compute
// that spawn offset; the list must stay at the top of this page.
Item {
    // Point size for the clips and the sticky; set from the font setting.
    property real fontSize: 12
    // Global font style; the labels pick bold/italic up from the font root in
    // Popup.qml, but FontMetrics is not an Item and has to be told.
    property string fontFamily: ""
    property bool fontBold: false
    property bool fontItalic: false
    property bool fontOutline: false
    // Background of the draft pad; set from the sticky colour setting.
    property string stickyColor: "#af9659"
    // Alpha in percent of the pad and the clip list surface; the send button
    // and all text stay opaque.
    property int innerOpacity: 90
    // Pad height in text lines as last dragged; 0 = the default. Lines rather
    // than pixels so the split keeps following the font size.
    property real padLines: 0

    readonly property real lineFactor: Sticky.lineFactor
    // Every row is two text lines tall, one-liners included, so the list
    // reads as an even grid and two-line entries show whole.
    readonly property int twoLines: Math.ceil(fm.lineSpacing * 2 * lineFactor)
    readonly property int rowHeight: twoLines + 12

    // The pad fits 6 lines by default, shrinking when a large font would
    // make that more than half the page. A dragged height is honoured up to
    // whatever leaves one clip row visible.
    readonly property int defaultPadLines: 6
    readonly property real padChrome: note.topPadding + note.bottomPadding
    // The pad's lines are set at the same factor as the clips (see blockFormat).
    readonly property real padLine: fm.lineSpacing * lineFactor
    readonly property real padHeight: {
        const lines = padLines > 0 ? padLines : defaultPadLines;
        const want = Math.ceil(lines * padLine + padChrome);
        const cap = padLines > 0 ? split.height - rowHeight - 8 : split.height / 2;
        return Math.max(Math.ceil(2 * padLine + padChrome), Math.min(want, cap));
    }
    onPadHeightChanged: pad.SplitView.preferredHeight = padHeight

    // Cursor goes to the end so typing continues the existing draft.
    function focusPad() {
        note.forceActiveFocus();
        note.cursorPosition = note.length;
    }

    // A hidden page's item keeps its focus, so typing on another page would
    // still land in the pad.
    function releaseFocus() {
        if (note.activeFocus) note.focus = false;
    }

    FontMetrics {
        id: fm
        font.pointSize: fontSize
        font.family: fontFamily
        font.bold: fontBold
        font.italic: fontItalic
    }

    // Emitted after a row is pasted; the window decides to close.
    signal picked()
    // Emitted when the user finishes dragging the split, in text lines.
    signal padResized(real lines)

    SplitView {
        id: split
        anchors.fill: parent
        orientation: Qt.Vertical

        // Dragging writes SplitView.preferredHeight directly, so the pad's
        // height is set imperatively (onPadHeightChanged) rather than bound.
        onResizingChanged: if (!resizing)
            padResized((pad.height - padChrome) / padLine)

        handle: Item {
            implicitHeight: 10

            // A short grab pill on the middle line.
            Rectangle {
                anchors.centerIn: parent
                width: 40
                height: 4
                radius: 2
                color: parent.SplitHandle.pressed || parent.SplitHandle.hovered
                    ? palette.highlight : palette.mid
            }
        }

        Item {
            SplitView.fillHeight: true
            SplitView.minimumHeight: rowHeight

            // The list's own surface, so it reads as an inner area like the pad.
            Rectangle {
                anchors.fill: parent
                radius: 8
                color: Qt.alpha(palette.base, innerOpacity / 100)
            }

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
                    // The style's own background is an opaque view colour,
                    // which would block the translucent panel.
                    background: Rectangle {
                        color: row.down ? Qt.alpha(palette.highlight, 0.35)
                            : row.hovered ? Qt.alpha(palette.highlight, 0.2) : "transparent"
                    }
                    onClicked: {
                        paster.paste(content);
                        picked();
                    }

                    contentItem: RowLayout {
                        spacing: 6

                        OutlineLabel {
                            id: label
                            outline: fontOutline
                            Layout.fillWidth: true
                            Layout.alignment: row.expanded ? Qt.AlignTop : Qt.AlignVCenter
                            font.pointSize: fontSize
                            lineHeight: lineFactor
                            text: row.content.trim()
                            // Anywhere as a fallback, so one long word cannot
                            // run under the ellipsis and arrow.
                            wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                            // Collapsed: two lines. No inline elide; the
                            // ellipsis sits in its own column on the right.
                            maximumLineCount: row.expanded ? 100000 : 2
                            clip: true
                        }

                        // Marks cut-off text at a fixed spot right before the
                        // arrow, rather than wherever the second line ends.
                        OutlineLabel {
                            outline: fontOutline
                            Layout.alignment: Qt.AlignVCenter
                            visible: !row.expanded && label.truncated
                            font.pointSize: fontSize
                            // Midline ellipsis: "…" sits on the baseline and
                            // would look low against the centred arrow.
                            text: "⋯"
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

            OutlineLabel {
                outline: fontOutline
                anchors.centerIn: parent
                visible: list.count === 0
                text: qsTr("No clipboard history yet")
                color: palette.placeholderText
            }
        }

        // Sticky-coloured pad; text stays near-black whatever the theme.
        Rectangle {
            id: pad
            SplitView.minimumHeight: Math.ceil(2 * padLine + padChrome)
            Component.onCompleted: SplitView.preferredHeight = padHeight
            radius: 8
            color: Qt.alpha(stickyColor, innerOpacity / 100)

            // A bare Flickable rather than a ScrollView: the TextArea clips
            // its text to its own height minus bottomPadding, so reserving
            // room for the button there hid the lines above it. The margin
            // adds scroll range past the end instead, and the text keeps the
            // full viewport.
            Flickable {
                anchors.fill: parent
                clip: true
                bottomMargin: sendButton.height + 16
                ScrollBar.vertical: ScrollBar {}

                // TextEdit has no outline style and Qt Quick ignores
                // QTextCharFormat.textOutline, so the outline is faked:
                // tinted copies of the pad one pixel around it, drawn under
                // the real text. Siblings of the TextArea, so they scroll
                // with it; the document itself is never touched.
                // One capture of the TextArea shared by all eight copies.
                ShaderEffectSource {
                    id: noteCapture
                    sourceItem: note
                    live: fontOutline
                    visible: false
                    width: note.width
                    height: note.height
                }

                Repeater {
                    model: fontOutline ? [[-1, -1], [0, -1], [1, -1], [-1, 0],
                                          [1, 0], [-1, 1], [0, 1], [1, 1]] : []

                    MultiEffect {
                        required property var modelData
                        source: noteCapture
                        x: note.x + modelData[0]
                        y: note.y + modelData[1]
                        width: note.width
                        height: note.height
                        z: -1
                        // Pushed to white or black: colorization scales by the
                        // source's luminance, so it cannot lighten dark glyphs.
                        // Opposite of the text colour, fully opaque.
                        brightness: note.color.hslLightness > 0.5 ? -1 : 1
                        // Drops the subpixel-AA colour of the captured glyphs.
                        saturation: -1
                    }
                }

                TextArea.flickable: TextArea {
                    id: note
                    wrapMode: TextArea.Wrap
                    font.pointSize: fontSize
                    // Native text is LCD-antialiased, and its coloured
                    // fringes show against the neutral outline.
                    renderType: fontOutline ? Text.CurveRendering : Text.NativeRendering
                    color: Sticky.ink(stickyColor)
                    background: null  // the pad supplies the colour
                    placeholderTextColor: Sticky.muted(stickyColor)
                    placeholderText: qsTr("Write a note…")
                    text: draft.content
                    Component.onCompleted: blockFormat.keep(textDocument, lineFactor)
                    // Written through on every edit. A reload that changes the
                    // text comes back here too, but setContent ignores a value
                    // that already matches the draft.
                    onTextChanged: if (text !== draft.content) draft.setContent(text)
                    Keys.onPressed: event => {
                        if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                                && (event.modifiers & Qt.ControlModifier)) {
                            draft.send();
                            event.accepted = true;
                        }
                    }
                }
            }

            // Floats over the text in a slight off-shade of the note: darker
            // on light colours, lighter on dark ones.
            RoundButton {
                id: sendButton
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 8
                width: 48
                height: 48
                enabled: note.text.trim().length > 0
                icon.name: "document-send"
                icon.width: 26
                icon.height: 26
                // Only the icon dims when blank: the background must stay visible.
                icon.color: enabled ? Sticky.ink(stickyColor) : Qt.alpha(Sticky.ink(stickyColor), 0.45)
                onClicked: draft.send()
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Send (Ctrl+Enter)")

                background: Rectangle {
                    radius: width / 2
                    readonly property bool light: Sticky.isLight(stickyColor)
                    readonly property real shade: sendButton.pressed ? 1.3
                        : sendButton.hovered ? 1.2 : 1.12
                    color: Qt.alpha(light ? Qt.darker(stickyColor, shade)
                                          : Qt.lighter(stickyColor, shade + 0.1), innerOpacity / 100)
                }
            }
        }
    }
}
