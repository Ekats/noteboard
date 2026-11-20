import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtCore
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

    // Distance from the popup's top edge to the middle of the first list
    // row. The daemon reads this to drop the pointer onto that row, so the
    // newest clipboard entry is already under the cursor on open.
    readonly property int firstRowOffset:
        layout.anchors.topMargin + topBar.height + layout.spacing + home.rowHeight / 2

    // Set false again on each show, so a popup that opens away from the
    // pointer does not immediately close. Arms once the mouse is inside.
    property bool leaveArmed: false

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
    height: 520
    color: "transparent"

    // Starts hidden: this is a resident daemon, shown on request over D-Bus.
    visible: false

    onVisibleChanged: {
        leaveTimer.stop();  // a close pending from the last show must not fire
        if (visible) leaveArmed = false;
    }

    Settings {
        id: config
        property bool closeOnMouseLeave: false
        property int historyLimit: 500  // 0 = unlimited
    }

    Binding {
        target: clipModel
        property: "limit"
        value: config.historyLimit
    }

    Rectangle {
        anchors.fill: parent
        radius: 8
        color: palette.window

        HoverHandler {
            onHoveredChanged: {
                if (hovered) {
                    popup.leaveArmed = true;
                    leaveTimer.stop();
                } else if (popup.leaveArmed && config.closeOnMouseLeave) {
                    leaveTimer.restart();
                }
            }
        }

        // Grace period, so brushing past the edge does not close the popup;
        // coming back inside within it cancels the close.
        Timer {
            id: leaveTimer
            interval: 1000
            onTriggered: popup.visible = false
        }

        ColumnLayout {
            id: layout
            anchors.fill: parent
            anchors.margins: 4
            spacing: 4

            RowLayout {
                id: topBar
                Layout.fillWidth: true
                spacing: 0

                ToolButton {
                    icon.name: "go-home"
                    checked: pages.currentIndex === 0
                    onClicked: pages.currentIndex = 0
                    ToolTip.visible: hovered
                    ToolTip.text: qsTr("Clipboard")
                }

                ToolButton {
                    icon.name: "settings-configure"
                    checked: pages.currentIndex === 1
                    onClicked: pages.currentIndex = 1
                    ToolTip.visible: hovered
                    ToolTip.text: qsTr("Settings")
                }

                Item { Layout.fillWidth: true }

                ToolButton {
                    icon.name: "window-close"
                    onClicked: popup.visible = false
                    ToolTip.visible: hovered
                    ToolTip.text: qsTr("Close")
                }
            }

            StackLayout {
                id: pages
                Layout.fillWidth: true
                Layout.fillHeight: true

                HomePage {
                    id: home
                    onPicked: popup.visible = false
                }
                SettingsPage { config: config }
            }
        }
    }

    // Esc dismisses. With an exclusive keyboard grab this is the only way
    // out from the keyboard, so it must exist before the window is shown.
    Shortcut {
        sequence: "Escape"
        onActivated: popup.visible = false
    }
}
