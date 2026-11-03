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

## Round 2 (after review): before* events and the keydown fallback

The stub now also cancels `beforepaste` (outside inputs) and `beforecopy` (after the editor's own
Ctrl+C), and the Ctrl+V keydown arms a next-task fallback that a `paste` event disarms. Same log
as above, and `FALLBACK-FIRED` never appears: in Chromium the `paste` event lands before the next
task, so the fallback cannot double-paste. WebKit and Firefox are not installed in this sandbox;
Safari relies on the cancelled `beforepaste` (WebKit's documented switch) and, failing that, the
keydown fallback for in-editor layers. Hand-test on Safari is in the PR's crew-handtest.
