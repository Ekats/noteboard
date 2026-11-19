import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    // The QtCore Settings object owned by Popup.qml, so values persist.
    required property var config

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 8

        Switch {
            text: qsTr("Close when mouse leaves")
            checked: config.closeOnMouseLeave
            onToggled: config.closeOnMouseLeave = checked
        }

        Item { Layout.fillHeight: true }
    }
}
