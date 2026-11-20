import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    // The QtCore Settings object owned by Popup.qml, so values persist.
    required property var config

    // 0 means unlimited.
    readonly property var historySteps: [50, 100, 250, 500, 1000, 2500, 5000, 0]

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 8

        Switch {
            text: qsTr("Close 1.5 s after the mouse leaves")
            checked: config.closeOnMouseLeave
            onToggled: config.closeOnMouseLeave = checked
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
