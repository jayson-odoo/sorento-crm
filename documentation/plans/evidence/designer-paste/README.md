# DESIGNER-PASTE: real Chromium clipboard check (3 Nov 2026)

`chromium-clipboard-check.js` (run with the sandbox's pre-installed Playwright, not a committed
spec) loads a stub page carrying the same window listeners `TagCanvasEditor` ships: keydown does
not cancel Ctrl+C/X/V, `beforecopy` is cancelled after the editor's own Ctrl+C, `beforepaste` is
cancelled outside inputs, `copy` writes `application/x-sorento-tag-layers`, `paste` reads the
clipboard. It puts a PNG on the system clipboard and presses real keys.

Output (Chromium on Linux, Ctrl):

```
keydown v
paste on DIV types=Files files=image/png:147 marker=
keydown c
copy: marker written
keydown v
paste on DIV types=text/plain,application/x-sorento-tag-layers files= marker=doc
keydown v
paste on INPUT types=text/plain files= marker=
input value: typed
```

So, in Chromium: an uncancelled Ctrl+V on a non-editable page fires `paste` with the screenshot
as a File; the editor's copy fires `copy` with nothing selected, and its marker replaces the
picture on the clipboard and is read back on the next paste; a paste inside an input is the
browser's.

Not covered here: macOS (Cmd routes through the app's Edit menu, so copy/paste events arrive
after the keydown's task) and WebKit/Firefox (not installed in this sandbox). The editor has no
keydown timer for Ctrl+V for that reason (it would race the late paste); Safari relies on the
cancelled `beforepaste`. On a Mac, a copy event that arrives after the next task finds the mark
already cleared, so the copied words go out through `navigator.clipboard.writeText` instead (a
single space for shape-only copies) and a paste of exactly those words reads back as the layers.
Both paths are in the owner's hand test.
