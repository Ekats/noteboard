import QtQuick
import QtQuick.Controls

// A Label that can outline its glyphs. The outline is the opposite tone of
// the text colour, so it reads on any background behind it.
Label {
    property bool outline: false

    style: outline ? Text.Outline : Text.Normal
    styleColor: color.hslLightness > 0.5 ? "black" : "white"
}
