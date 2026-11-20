.pragma library

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

// Markdown folds a single newline into a space, but a sticky note (and Memos)
// shows it as a line break. Display only: appends a hard break to a line
// whose next line continues the same block, leaving blank-line paragraph
// breaks, list items and fenced code alone.
function breakLines(text) {
    var lines = text.split("\n");
    var fenced = false;
    var fence = /^\s*(```|~~~)/;
    var item = /^\s*([-*+]|\d+[.)])\s/;
    return lines.map(function (line, i) {
        var isFence = fence.test(line);
        if (isFence)
            fenced = !fenced;
        if (i === lines.length - 1 || isFence || fenced)
            return line;
        var next = lines[i + 1];
        if (line.trim() === "" || next.trim() === "" || fence.test(next) || item.test(next)
                || / {2}$|\\$/.test(line))
            return line;
        return line + "  ";
    }).join("\n");
}

// Placeholder and timestamps: the ink at reduced opacity (#AARRGGBB).
function muted(hex) {
    return isLight(hex) ? "#b01d1b16" : "#b0f4f1e8";
}
