import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    // The QtCore Settings object owned by Popup.qml, so values persist.
    required property var config

    // The default first, then the same muted tone around the hue wheel: the
    // default's lightness, slightly less saturation so cool hues do not
    // read louder than the warm tan. Clay, rose, mauve, slate, teal, sage,
    // olive.
    readonly property var stickyColors: ["#af9659", "#a27a66", "#a26670", "#8967a2",
                                         "#667aa2", "#669da2", "#66a27a", "#89a266"]

    // A drag of one opacity slider to v. Linked, the other one moves by the
    // same delta, which is limited so neither leaves 30-100 and the offset
    // between them holds. The dragged handle is put back on the allowed
    // value: a drag breaks the slider's value binding.
    function moveOpacity(v, outer) {
        const mine = outer ? config.opacity : config.innerOpacity;
        const other = outer ? config.innerOpacity : config.opacity;
        let delta = v - mine;
        if (config.linkOpacity)
            delta = Math.max(30 - Math.min(mine, other), Math.min(100 - Math.max(mine, other), delta));
        else
            delta = Math.max(30, Math.min(100, v)) - mine;
        if (outer) {
            config.opacity = mine + delta;
            if (config.linkOpacity) config.innerOpacity = other + delta;
        } else {
            config.innerOpacity = mine + delta;
            if (config.linkOpacity) config.opacity = other + delta;
        }
        outerSlider.value = config.opacity;
        innerSlider.value = config.innerOpacity;
    }

    // 0 means unlimited.
    readonly property var historySteps: [50, 100, 250, 500, 1000, 2500, 5000, 0]

    // The Memos section pushed the page past the panel height.
    Flickable {
      id: scroller
      anchors.fill: parent
      contentHeight: column.height + 16
      clip: true
      boundsBehavior: Flickable.StopAtBounds
      ScrollBar.vertical: ScrollBar {}

    ColumnLayout {
        id: column
        x: 8
        y: 8
        width: scroller.width - 16
        height: Math.max(implicitHeight, scroller.height - 16)
        spacing: 8

        Switch {
            text: qsTr("Close 1 s after the mouse leaves")
            checked: config.closeOnMouseLeave
            onToggled: config.closeOnMouseLeave = checked
        }

        RowLayout {
            OutlineLabel {
                outline: config.fontOutline
                Layout.fillWidth: true
                text: qsTr("Font size")
            }
            SpinBox {
                from: 8
                to: 24
                value: config.fontSize
                onValueModified: config.fontSize = value
            }

            // Global UI font style, not just clips and notes.
            ToolButton {
                icon.name: "format-text-bold"
                checkable: true
                checked: config.fontBold
                onToggled: config.fontBold = checked
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Bold")
            }
            ToolButton {
                icon.name: "format-text-italic"
                checkable: true
                checked: config.fontItalic
                onToggled: config.fontItalic = checked
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Italic")
            }
            // Breeze has no text-outline icon; the stroke one is the closest.
            ToolButton {
                icon.name: "format-stroke-color"
                checkable: true
                checked: config.fontOutline
                onToggled: config.fontOutline = checked
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Outline")
            }
        }

        // A filterable family picker. Not an editable ComboBox: that one
        // autocompletes inline and rewrites its text when the model narrows,
        // which fights a type-to-filter list. The list is an in-window Popup,
        // which matters: a second window could not take focus here.
        TextField {
            id: family
            Layout.fillWidth: true
            // The first entry stands for the empty (system) family.
            readonly property string systemDefault: qsTr("System default")
            readonly property var families: [systemDefault].concat(Qt.fontFamilies())
            readonly property string shown: config.fontFamily !== "" ? config.fontFamily : systemDefault
            // What the user typed; the full list while the text is the
            // untouched current family.
            readonly property string query: activeFocus && text !== shown ? text.toLowerCase() : ""
            readonly property var matches: query === "" ? families
                : families.filter(f => f.toLowerCase().includes(query))

            function pick(name) {
                config.fontFamily = name === systemDefault ? "" : name;
                list.close();
                focus = false;
            }

            text: shown
            selectByMouse: true
            // Resting state shows the current family, in its own face.
            font.family: config.fontFamily !== "" ? config.fontFamily : Qt.application.font.family
            onActiveFocusChanged: {
                if (activeFocus) {
                    selectAll();
                    list.open();
                } else {
                    list.close();
                    text = Qt.binding(() => shown);
                }
            }
            onAccepted: if (matches.length > 0) pick(matches[0])
            Keys.onDownPressed: list.open()

            Popup {
                id: list
                // Room under and over the field inside this page. The window
                // also holds the shadow margin, which receives no pointer
                // input, so the list must stay within the page; it opens
                // upward when there is more room there.
                property real below: 0
                property real above: 0
                readonly property bool flip: below < 120 && above > below
                y: flip ? -height : family.height
                width: family.width
                height: Math.min(220, view.contentHeight + 2 * padding, flip ? above : below)
                padding: 1
                focus: false  // the field keeps the keyboard
                closePolicy: Popup.CloseOnEscape
                onAboutToShow: {
                    const top = family.mapToItem(page, 0, 0).y;
                    above = top;
                    below = page.height - top - family.height;
                }

                // Each family in its own face; the list is virtualised, so
                // only the visible rows are built.
                contentItem: ListView {
                    id: view
                    clip: true
                    model: family.matches
                    ScrollBar.vertical: ScrollBar {}

                    delegate: ItemDelegate {
                        required property int index
                        required property string modelData
                        width: ListView.view.width
                        // A click must not pull focus off the field, which
                        // would close the list before the click lands.
                        focusPolicy: Qt.NoFocus
                        text: modelData
                        font.family: modelData === family.systemDefault
                            ? Qt.application.font.family : modelData
                        highlighted: modelData === family.shown
                        onClicked: family.pick(modelData)
                    }
                }
            }
        }

        OutlineLabel { outline: config.fontOutline; text: qsTr("Sticky colour") }

        // Inline on purpose: a ColorDialog would be a second window, and with
        // layer-shell integration global to the process it could not take focus.
        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            Repeater {
                model: stickyColors

                Rectangle {
                    required property string modelData
                    readonly property bool selected: modelData === config.stickyColor.toLowerCase()

                    Layout.preferredWidth: 26
                    Layout.preferredHeight: 26
                    radius: 13
                    color: modelData
                    border.width: selected ? 3 : 1
                    border.color: selected ? palette.highlight : palette.mid

                    TapHandler { onTapped: config.stickyColor = parent.modelData }
                }
            }

            Item { Layout.fillWidth: true }

            TextField {
                id: hex
                Layout.preferredWidth: 90
                text: config.stickyColor
                maximumLength: 7
                validator: RegularExpressionValidator { regularExpression: /#[0-9a-fA-F]{6}/ }
                // editingFinished does not fire for an unacceptable value, so
                // an invalid entry is reverted when focus leaves instead.
                onEditingFinished: config.stickyColor = text.toLowerCase()
                onActiveFocusChanged: if (!activeFocus) text = config.stickyColor

                Connections {
                    target: config
                    function onStickyColorChanged() { hex.text = config.stickyColor }
                }
            }
        }

        OutlineLabel { outline: config.fontOutline; text: qsTr("Window background") }

        RowLayout {
            Layout.fillWidth: true

            Slider {
                id: outerSlider
                Layout.fillWidth: true
                from: 30
                to: 100
                stepSize: 5
                snapMode: Slider.SnapAlways
                value: config.opacity
                onMoved: moveOpacity(Math.round(value), true)
            }

            OutlineLabel {
                outline: config.fontOutline
                Layout.minimumWidth: 70
                horizontalAlignment: Text.AlignRight
                text: qsTr("%1 %").arg(config.opacity)
            }
        }

        RowLayout {
            Layout.fillWidth: true

            OutlineLabel {
                outline: config.fontOutline
                Layout.fillWidth: true
                text: qsTr("Notes and clipboard")
            }

            ToolButton {
                id: linkButton
                icon.name: "link"
                checkable: true
                checked: config.linkOpacity
                onToggled: config.linkOpacity = checked
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Move both sliders together")
            }
        }

        RowLayout {
            Layout.fillWidth: true

            Slider {
                id: innerSlider
                Layout.fillWidth: true
                from: 30
                to: 100
                stepSize: 5
                snapMode: Slider.SnapAlways
                value: config.innerOpacity
                onMoved: moveOpacity(Math.round(value), false)
            }

            OutlineLabel {
                outline: config.fontOutline
                Layout.minimumWidth: 70
                horizontalAlignment: Text.AlignRight
                text: qsTr("%1 %").arg(config.innerOpacity)
            }
        }

        OutlineLabel { outline: config.fontOutline; text: qsTr("Clipboard history") }

        RowLayout {
            Layout.fillWidth: true

            Slider {
                id: historySlider
                Layout.fillWidth: true
                from: 0
                to: historySteps.length - 1
                stepSize: 1
                snapMode: Slider.SnapAlways
                value: {
                    const i = historySteps.indexOf(config.historyLimit);
                    return i >= 0 ? i : historySteps.indexOf(500);
                }
                // Lowering the limit prunes immediately, so only commit on
                // release: committing every step of a drag would delete
                // history the user passed through but did not settle on.
                function commit() { config.historyLimit = historySteps[Math.round(value)] }
                onMoved: if (!pressed) commit()  // keyboard
                onPressedChanged: if (!pressed) commit()
            }

            OutlineLabel {
                outline: config.fontOutline
                Layout.minimumWidth: 70
                horizontalAlignment: Text.AlignRight
                text: {
                    const n = historySteps[Math.round(historySlider.value)];
                    return n === 0 ? qsTr("Unlimited") : n;
                }
            }
        }

        OutlineLabel { outline: config.fontOutline; text: qsTr("Memos sync") }

        Switch {
            text: qsTr("Sync with a Memos server")
            checked: config.memosEnabled
            onToggled: config.memosEnabled = checked
        }

        TextField {
            id: memosUrl
            Layout.fillWidth: true
            placeholderText: qsTr("Server URL, e.g. https://memos.example.com")
            text: config.memosUrl
            inputMethodHints: Qt.ImhUrlCharactersOnly
            onEditingFinished: config.memosUrl = text.trim()
        }

        RowLayout {
            Layout.fillWidth: true

            TextField {
                id: memosToken
                Layout.fillWidth: true
                echoMode: TextInput.Password
                placeholderText: config.memosTokenSet ? qsTr("Token saved")
                                                      : qsTr("Access token")
                onAccepted: saveToken()
                function saveToken() {
                    if (text === "") return;
                    syncController.saveToken(text);
                    text = "";  // never keep the secret in the UI
                }
            }
            Button {
                text: qsTr("Save")
                enabled: memosToken.text !== ""
                onClicked: memosToken.saveToken()
            }
            Button {
                text: qsTr("Clear")
                visible: config.memosTokenSet
                onClicked: syncController.saveToken("")
            }
        }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: qsTr("Sync now")
                enabled: config.memosEnabled && config.memosUrl !== ""
                         && config.memosTokenSet && !syncController.syncing
                onClicked: syncController.syncNow()
            }
            OutlineLabel {
                id: memosStatus
                outline: config.fontOutline
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: page.tokenError !== "" ? page.tokenError
                    : !config.memosEnabled ? qsTr("Sync is off")
                    : config.memosUrl === "" ? qsTr("Enter the server URL")
                    : !config.memosTokenSet ? qsTr("Add an access token")
                    : syncController.syncing ? qsTr("Syncing…")
                    : syncController.status !== "" ? syncController.status
                    : qsTr("Not synced yet")
            }
        }

        Item { Layout.fillHeight: true }

        Button {
            id: quitButton
            Layout.fillWidth: true
            text: qsTr("Quit NoteBoard")
            // Exit code 0, so a systemd Restart=on-failure leaves it quit.
            onClicked: Qt.quit()
            ToolTip.visible: hovered
            ToolTip.text: qsTr("Stops clipboard capture until the next login or start")
            contentItem: Label {
                text: quitButton.text
                color: "white"
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                radius: 4
                // Breeze negative red, lightened a step on hover/press.
                color: quitButton.down ? "#b8303f"
                     : quitButton.hovered ? "#e5606d" : "#da4453"
            }
        }
    }
    }

    // Last failed token save/clear, shown in place of the sync status.
    property string tokenError: ""
    Connections {
        target: syncController
        function onTokenStored(ok, isSet, error) { page.tokenError = ok ? "" : error }
    }
}
