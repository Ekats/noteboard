// KWin script: the global shortcut and the pointer position.
//
// Both live here because a Wayland client can do neither for itself. Qt
// cannot query the global pointer position, and kglobalaccel will not
// dispatch a shortcut to a plain client. KWin can do both, so it reads the
// pointer on keypress and hands the result to the daemon over D-Bus.
//
// Coordinates sent are relative to the output the pointer is on, because
// layer-shell margins are output-relative while workspace.cursorPos is in
// global compositor coordinates.

function showPopupAtPointer() {
    var p = workspace.cursorPos;
    var screen = workspace.screenAt(p);
    if (!screen) {
        return;
    }
    var g = screen.geometry;
    callDBus("io.github.ekats.noteboard", "/Popup", "", "showAt",
             Math.round(p.x - g.x), Math.round(p.y - g.y), screen.name);
}

registerShortcut("NoteboardShowPopup",
                 "NoteBoard: show popup at pointer",
                 "Meta+Shift+V",
                 showPopupAtPointer);
