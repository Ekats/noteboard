import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    // The QtCore Settings object owned by Popup.qml, so values persist.
    required property var config

    // The default first, then the same muted tone around the hue wheel: the
    // default's lightness, slightly less saturation so cool hues do not
    // read louder than the warm tan. Clay, rose, mauve, slate, teal, sage,
    // olive.
    readonly property var stickyColors: ["#af9659", "#a27a66", "#a26670", "#8967a2",
                                         "#667aa2", "#669da2", "#66a27a", "#89a266"]

    // 0 means unlimited.
    readonly property var historySteps: [50, 100, 250, 500, 1000, 2500, 5000, 0]

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 8

        Switch {
            text: qsTr("Close 1 s after the mouse leaves")
            checked: config.closeOnMouseLeave
            onToggled: config.closeOnMouseLeave = checked
        }

        RowLayout {
            Label {
                Layout.fillWidth: true
                text: qsTr("Font size")
            }
            SpinBox {
                from: 8
                to: 24
                value: config.fontSize
                onValueModified: config.fontSize = value
            }
        }

        Label { text: qsTr("Sticky colour") }

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

        Label { text: qsTr("Window background") }

        RowLayout {
            Layout.fillWidth: true

            Slider {
                Layout.fillWidth: true
                from: 30
                to: 100
                stepSize: 5
                snapMode: Slider.SnapAlways
                value: config.opacity
                onMoved: config.opacity = Math.round(value)
            }

            Label {
                Layout.minimumWidth: 70
                horizontalAlignment: Text.AlignRight
                text: qsTr("%1 %").arg(config.opacity)
            }
        }

        Label { text: qsTr("Notes and clipboard") }

        RowLayout {
            Layout.fillWidth: true

            Slider {
                Layout.fillWidth: true
                from: 30
                to: 100
                stepSize: 5
                snapMode: Slider.SnapAlways
                value: config.innerOpacity
                onMoved: config.innerOpacity = Math.round(value)
            }

            Label {
                Layout.minimumWidth: 70
                horizontalAlignment: Text.AlignRight
                text: qsTr("%1 %").arg(config.innerOpacity)
            }
        }

        Label { text: qsTr("Clipboard history") }

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

            Label {
                Layout.minimumWidth: 70
                horizontalAlignment: Text.AlignRight
                text: {
                    const n = historySteps[Math.round(historySlider.value)];
                    return n === 0 ? qsTr("Unlimited") : n;
                }
            }
        }

        Item { Layout.fillHeight: true }
    }
}
