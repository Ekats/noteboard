import QtQuick
import QtQuick.Controls

// Clipboard history. The list itself is not built yet; the pointer is aimed
// at where its first row will be, so the spawn position stays correct once
// the rows arrive.
Item {
    Label {
        anchors.centerIn: parent
        text: qsTr("Clipboard history goes here")
        color: palette.placeholderText
    }
}
