# DESIGNER-PASTE: real Chromium clipboard check (3 Nov 2026)

`chromium-clipboard-check.js` (run with the sandbox's pre-installed Playwright, not a committed
spec) loads a stub page carrying the same window listeners as `TagCanvasEditor` (keydown not
cancelled, `copy` writes `application/x-sorento-tag-layers`, `paste` reads the clipboard), puts a
PNG on the system clipboard, then presses real keys.

Observed log:

```
kd:v   -> paste on DIV  types=[Files]  files=[image/png:147]            (screenshot reaches the paste event)
kd:c   -> copy-marked                                                    (copy fires with nothing selected)
kd:v   -> paste on DIV  types=[text/plain, application/x-sorento-tag-layers] marker=doc text=words
kd:v   -> paste on INPUT text=typed, input value "typed"                 (input paste stays native)
```

So: an uncancelled Ctrl+V keydown is followed by a `paste` event carrying the image as a File; the
editor's copy marker replaces whatever image was on the clipboard and is read back on the next
paste; a paste inside an input is the browser's.
