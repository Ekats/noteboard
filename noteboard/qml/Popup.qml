import QtQuick
import QtQuick.Controls
import org.kde.layershell as LayerShell

// The popup surface. Uses wlr-layer-shell so it can place itself at an
// arbitrary point on the output and take a real keyboard grab -- neither is
// possible with xdg-shell.
//
// Placement trick: anchor to the top-left corner, then use left/top margins
// as absolute coordinates. Margins are output-relative, so originX/originY
// arrive already converted; see noteboard/kwin/noteboard.js.
Window {
    id: popup

    property int originX: 0
    property int originY: 0

    // The output to put the surface on. LayerShellQt reads its own screen
    // property rather than QWindow.screen(), so this has to be set
    // explicitly or the surface lands on the primary output.
    property var targetScreen: null

    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityExclusive
    // qmllint reports this as QVariantMap -> QMargins; it is the documented
    // value-type coercion and the linter just cannot see it statically.
    LayerShell.Window.margins: ({ left: originX, top: originY, right: 0, bottom: 0 })
    LayerShell.Window.scope: "noteboard-popup"
    LayerShell.Window.activateOnShow: true
    LayerShell.Window.screenConfiguration: LayerShell.Window.ScreenFromQWindow
    LayerShell.Window.screen: targetScreen

    width: 400
    height: 500
    color: "transparent"

    // Starts hidden: this is a resident daemon, shown on request over D-Bus.
    visible: false

    Rectangle {
        anchors.fill: parent
        radius: 8
        color: palette.window

        Label {
            anchors.centerIn: parent
            text: "popup at " + popup.originX + "," + popup.originY
            horizontalAlignment: Text.AlignHCenter
        }
    }

    // Esc dismisses. With an exclusive keyboard grab this is the only way
    // out, so it must exist before the window is ever shown.
    Shortcut {
        sequence: "Escape"
        onActivated: popup.visible = false
    }
}
