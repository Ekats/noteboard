import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
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

    // The visible panel; the window is this plus a transparent margin on all
    // sides that holds the drop shadow. The daemon positions and clamps the
    // panel, and restricts input to it.
    readonly property int panelWidth: 400
    readonly property int panelHeight: 520
    readonly property int shadowMargin: 32

    // Distance from the window's top edge to the middle of the first list
    // row. The daemon reads this to drop the pointer onto that row, so the
    // newest clipboard entry is already under the cursor on open.
    readonly property int firstRowOffset:
        shadowMargin + layout.anchors.topMargin + topBar.height + layout.spacing + home.rowHeight / 2

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

    width: panelWidth + 2 * shadowMargin
    height: panelHeight + 2 * shadowMargin
    color: "transparent"

    // Starts hidden: this is a resident daemon, shown on request over D-Bus.
    visible: false

    // Dropdowns, menus and tooltips live in the window's overlay layer, not in
    // the panel, so the panel's HoverHandler reports "left" while the pointer
    // is over them. Any visible overlay child therefore counts as inside.
    // Tooltips count too: they hide as soon as the pointer leaves their
    // control, and that hide re-runs updateLeave, so they cannot pin the popup.
    readonly property bool overlayOpen: Overlay.overlay !== null && Overlay.overlay.visibleChildren.length > 0

    // The one place that decides whether the close timer runs.
    function updateLeave() {
        const outside = leaveArmed && config.closeOnMouseLeave
            && !panelHover.hovered && !overlayOpen;
        if (!outside) leaveTimer.stop();
        else if (!leaveTimer.running) leaveTimer.start();
    }

    // Visible page, settable from the daemon: 0 capture, 1 notes, 2 settings.
    property alias page: pages.currentIndex

    // Re-evaluate when the last overlay popup closes (or the first opens).
    onOverlayOpenChanged: updateLeave()

    onVisibleChanged: {
        leaveTimer.stop();  // a close pending from the last show must not fire
        if (visible) {
            leaveArmed = false;
            // place() reloaded the list already, so only drop the state.
            notes.editingId = "";
            Qt.callLater(focusPad);
        } else {
            notes.finishEdit();
        }
    }

    // The surface is recreated and activated asynchronously after each show,
    // and the daemon sets the page around it, so every trigger funnels here
    // and only acts once visible and active hold. Off Capture the hidden pad
    // would otherwise keep the keyboard focus and swallow typing.
    function focusPad() {
        if (!visible || !active) return;
        if (pages.currentIndex === 0) home.focusPad();
        else home.releaseFocus();
    }
    onActiveChanged: focusPad()

    Settings {
        id: config
        property bool closeOnMouseLeave: false
        property int historyLimit: 500  // 0 = unlimited
        property int fontSize: 12  // points, clips and sticky
        property string stickyColor: "#af9659"  // default for the pad and notes without their own
        property real padLines: 0  // dragged draft pad height in text lines; 0 = default
        property int opacity: 80  // percent, panel background only
        property int innerOpacity: 90  // percent, pad, note cards and clip list surfaces
        property bool linkOpacity: false  // the two sliders move together
        property string fontFamily: ""  // all UI text; empty = the system font
        property bool fontBold: false
        property bool fontItalic: false
        property bool fontOutline: false
        property bool memosEnabled: false
        property string memosUrl: ""  // the access token lives in the secret store, not here
        property bool memosTokenSet: false  // whether the secret store holds one
    }

    Binding {
        target: clipModel
        property: "limit"
        value: config.historyLimit
    }

    Binding { target: syncController; property: "enabled"; value: config.memosEnabled }
    Binding { target: syncController; property: "serverUrl"; value: config.memosUrl }
    Binding { target: syncController; property: "tokenSet"; value: config.memosTokenSet }
    // A sync that finishes mid-edit reloads the list after the edit ends.
    Binding { target: syncController; property: "editing"; value: notes.editing }

    Connections {
        target: syncController
        function onTokenStored(ok, isSet, error) {
            if (ok) config.memosTokenSet = isSet;
        }
    }

    // Breeze-like drop shadow. It is cut out under the panel, so a translucent
    // panel does not show a dark slab through itself.
    // The layer is the whole window: a layer is clipped to its item, and the
    // blur reaches past the panel.
    Item {
        anchors.fill: parent
        layer.enabled: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskInverted: true
            maskSource: hole
            maskThresholdMin: 0.5
            maskSpreadAtMin: 1.0
        }

        RectangularShadow {
            x: panel.x
            y: panel.y + 2
            width: panel.width
            height: panel.height
            radius: panel.radius
            blur: 28
            spread: 4
            color: "#cc000000"
        }
    }

    // Mask source for the cut-out above: the panel's footprint.
    Item {
        id: hole
        anchors.fill: parent
        visible: false
        layer.enabled: true

        Rectangle {
            x: panel.x
            y: panel.y
            width: panel.width
            height: panel.height
            radius: panel.radius
        }
    }

    Rectangle {
        id: panel
        x: shadowMargin
        y: shadowMargin
        width: panelWidth
        height: panelHeight
        radius: 8
        color: "transparent"

        // The translucent background. Alpha on the colour, not Item.opacity,
        // so the content stays opaque. On Capture and Notes it is cut out
        // under the inner surfaces: they are drawn at their own alpha, and
        // over this one the two would compound (inner could never look more
        // transparent than outer).
        Rectangle {
            id: panelBg
            anchors.fill: parent
            radius: panel.radius
            color: Qt.alpha(palette.window, config.opacity / 100)
            layer.enabled: pages.currentIndex < 2
            layer.effect: MultiEffect {
                maskEnabled: true
                maskInverted: true
                maskSource: surfaceMask
                // Inner surfaces are at least 30 % alpha; anything above
                // this counts as a hole. The spread softens the edge.
                maskThresholdMin: 0.1
                maskSpreadAtMin: 0.1
            }
        }

        HoverHandler {
            id: panelHover
            onHoveredChanged: {
                if (hovered) popup.leaveArmed = true;
                popup.updateLeave();
            }
        }

        // Grace period, so brushing past the edge does not close the popup;
        // coming back inside within it cancels the close.
        Timer {
            id: leaveTimer
            interval: 1000
            onTriggered: if (!popup.overlayOpen) popup.visible = false
        }

        // The plain Window above has no font of its own to hand down, so this
        // Control is the font root: every Control and Label below inherits
        // family/bold/italic from it, and explicit sizes elsewhere still win.
        Control {
            id: ui
            anchors.fill: parent
            // An empty family would not mean "default" to the font system.
            font.family: config.fontFamily !== "" ? config.fontFamily : Qt.application.font.family
            font.bold: config.fontBold
            font.italic: config.fontItalic

        ColumnLayout {
            id: layout
            anchors.fill: parent
            anchors.margins: 4
            spacing: 4

            Item {
                id: topBar
                Layout.fillWidth: true
                implicitHeight: Math.max(settingsButton.implicitHeight, tabs.implicitHeight)

                ToolButton {
                    id: settingsButton
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    icon.name: "settings-configure"
                    checked: pages.currentIndex === 2
                    onClicked: pages.currentIndex = 2
                    ToolTip.visible: hovered
                    ToolTip.text: qsTr("Settings")
                }

                // Centred on the popup rather than in the space between the
                // buttons, hence anchors instead of layout slots.
                TabBar {
                    id: tabs
                    // Fixed so the labels are not elided to the TabBar's
                    // initial implicit width.
                    width: 220
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.verticalCenter: parent.verticalCenter

                    TabButton {
                        id: captureTab
                        text: qsTr("Capture")
                        onClicked: pages.currentIndex = 0
                    }
                    TabButton {
                        id: notesTab
                        text: qsTr("Notes")
                        onClicked: pages.currentIndex = 1
                    }
                }

                // Driven per button, not through TabBar.currentIndex: -1
                // there leaves the old tab looking checked. A click assigns
                // checked, which would drop a plain binding; Binding keeps
                // following the page. Neither tab is checked on settings.
                Binding {
                    target: captureTab
                    property: "checked"
                    value: pages.currentIndex === 0
                }
                Binding {
                    target: notesTab
                    property: "checked"
                    value: pages.currentIndex === 1
                }

                ToolButton {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
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
                onCurrentIndexChanged: {
                    if (currentIndex !== 1) notes.finishEdit();
                    Qt.callLater(popup.focusPad);
                }

                HomePage {
                    id: home
                    fontSize: config.fontSize
                    fontFamily: ui.font.family
                    fontBold: config.fontBold
                    fontItalic: config.fontItalic
                    fontOutline: config.fontOutline
                    stickyColor: config.stickyColor
                    innerOpacity: config.innerOpacity
                    padLines: config.padLines
                    onPicked: popup.visible = false
                    onPadResized: lines => config.padLines = lines
                }
                NotesPage {
                    id: notes
                    fontSize: config.fontSize
                    fontOutline: config.fontOutline
                    stickyColor: config.stickyColor
                    innerOpacity: config.innerOpacity
                }
                SettingsPage { config: config }
            }
        }
        }
    }

    // Mask source for panelBg: a live copy of the current page, placed over
    // the panel. Only its inner surfaces have alpha worth a hole; it stops
    // updating while hidden and on Settings, which has none.
    Item {
        id: surfaceMask
        x: panel.x
        y: panel.y
        width: panel.width
        height: panel.height
        visible: false
        layer.enabled: true

        ShaderEffectSource {
            x: layout.x + pages.x
            y: layout.y + pages.y
            width: pages.width
            height: pages.height
            live: popup.visible && pages.currentIndex < 2
            hideSource: false
            sourceItem: pages.currentIndex === 1 ? notes : home
        }
    }

    // Esc dismisses. With an exclusive keyboard grab this is the only way
    // out from the keyboard, so it must exist before the window is shown.
    // A shortcut runs before any item's key handler, so the edit-in-progress
    // case is decided here: Esc ends the edit first, and only then closes.
    Shortcut {
        sequence: "Escape"
        onActivated: if (notes.editing) notes.finishEdit(); else popup.visible = false
    }
}
