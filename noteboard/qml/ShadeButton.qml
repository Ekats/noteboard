import QtQuick
import QtQuick.Controls
import "sticky.js" as Sticky

// A round ToolButton with an always-visible off-shade of the surface it sits
// on (darker on light colours, lighter on dark), so it reads as a button.
ToolButton {
    id: control

    // The surface colour, "#RRGGBB".
    property string base
    // Alpha of the surface in percent; the icon stays opaque.
    property int surfaceOpacity: 100

    padding: 0
    icon.color: Sticky.ink(base)

    background: Rectangle {
        // Inset so neighbouring circles in a row do not touch.
        anchors.fill: parent
        anchors.margins: 2
        radius: width / 2
        color: Sticky.buttonFill(control.base, control.pressed ? 2 : control.hovered ? 1 : 0,
                                 control.surfaceOpacity / 100)
    }
}
