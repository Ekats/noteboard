.pragma library

// Line height multiplier for all text: a touch tighter than the font's
// natural spacing.
var lineFactor = 0.92;

// Text colours for a sticky background given as "#RRGGBB": near-black on
// light colours, near-white on dark ones, switching where the two give equal
// contrast (relative luminance 0.179).
function luminance(hex) {
    var channels = [1, 3, 5].map(function (i) {
        var c = parseInt(hex.substr(i, 2), 16) / 255;
        return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function isLight(hex) {
    return luminance(hex) > 0.179;
}

function ink(hex) {
    return isLight(hex) ? "#1d1b16" : "#f4f1e8";
}

// Fill of a round button on a surface given as "#RRGGBB": an off-shade, darker
// on light surfaces and lighter on dark ones (which need the extra 0.1 to read
// as much). level 0 = rest, 1 = hovered, 2 = pressed. The one place the
// button shade steps live, shared by ShadeButton and the Capture send button.
function buttonFill(hex, level, opacity) {
    var shade = [1.3, 1.4, 1.5][level];
    return Qt.alpha(isLight(hex) ? Qt.darker(hex, shade) : Qt.lighter(hex, shade + 0.1),
                    opacity);
}

// Markdown folds a single newline into a space, but a sticky note (and Memos)
// shows it as a line break. Display only. Qt's Markdown reader turns a
// "  \n" hard break into a new paragraph block with paragraph margins (a
// pitch of ~1.27 wrapped lines), so plain text lines are instead joined with
// U+2028, a real line break inside one block, at the same pitch as wrapping.
// Blank-line paragraph breaks stay paragraphs. Lines that start or are
// Markdown block syntax (lists, fences, headings, quotes, tables, rules,
// indented code) keep the old "  \n" break so the syntax still parses.
var LINE_SEP = "\u2028";

function breakLines(text) {
    var lines = text.split("\n");
    var fenced = false;
    var fence = /^\s*(```|~~~)/;
    var item = /^\s*([-*+]|\d+[.)])\s/;
    var syntax = /^(\s{4,}|\t|#{1,6}(\s|$)|>|\||\s*([-*_=])(\s*\3){2,}\s*$)/;
    var out = "";
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        var isFence = fence.test(line);
        if (isFence)
            fenced = !fenced;
        if (i === lines.length - 1) {
            out += line;
            break;
        }
        var next = lines[i + 1];
        if (isFence || fenced || line.trim() === "" || next.trim() === ""
                || fence.test(next) || item.test(next) || /\\$/.test(line)) {
            out += line + "\n";
        } else if (item.test(line) || syntax.test(line) || syntax.test(next)) {
            out += (/ {2}$/.test(line) ? line : line + "  ") + "\n";
        } else {
            out += line.replace(/ {2}$/, "") + LINE_SEP;
        }
    }
    return out;
}

// Placeholder and timestamps: the ink at reduced opacity (#AARRGGBB).
function muted(hex) {
    return isLight(hex) ? "#b01d1b16" : "#b0f4f1e8";
}
