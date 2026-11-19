import QtQuick
import QtQuick.Controls
import org.kde.layershell as LayerShell

// The popup surface. Uses wlr-layer-shell so it can place itself at an
// arbitrary point on the output and take a real keyboard grab -- neither is
// possible with xdg-shell.
//
// Placement trick: anchor to the top-left corner, then use left/top margins
// as absolute coordinates.
Window {
    id: popup

    property int originX: 0
    property int originY: 0

    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityExclusive
    LayerShell.Window.margins: Qt.rect(originX, originY, 0, 0)
    LayerShell.Window.scope: "noteboard-popup"
    LayerShell.Window.activateOnShow: true

    width: 400
    height: 500
    color: "transparent"
    visible: true

    Rectangle {
        anchors.fill: parent
        radius: 8
        color: palette.window

        Label {
            anchors.centerIn: parent
            text: "layer-shell popup\n" + popup.originX + "," + popup.originY
            horizontalAlignment: Text.AlignHCenter
        }
    }

    // Esc dismisses. With an exclusive grab this is the only way out, so it
    // must exist before the window is ever shown.
    Shortcut {
        sequence: "Escape"
        onActivated: Qt.quit()
    }
}
