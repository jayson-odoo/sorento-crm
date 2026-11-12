# PLAN: MAIN-RED-TAGSHEET (12 Nov 2026)

Status: in progress. Small fix track (one frontend function, two new test files, no migration, no auth/RBAC change).

## Problem

Crew's pre-merge census (fresh `npm ci`) found
`sorento_crm_frontend/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer.rich-text.test.tsx`
"AC-17: an <img onerror> string in a rich description renders as visible text, no img element" red on origin/main
42f418bd74: `expected '<imgsrc=xonerror=alert(1)>' to contain '<img src=x onerror=alert(1)>'`.

## Diagnosis (measured)

- On this Mac the file is green (6/6) after a fresh `npm ci --force`, because the optional dependency `canvas`
  (`sorento_crm_frontend/package.json` `optionalDependencies`) built, so jsdom hands out a real 2D context.
- Hide `node_modules/canvas` and the same test fails with the census's exact assertion. So the census machine ran
  without the optional `canvas` package (why it was missing there: UNVERIFIED).
- Cause: `richLayerLines` (`sorento_crm_frontend/lib/dealer-kit/text-layout.ts`) decides "the line has started" with
  `lineWidth > 0`. With no measure (no canvas: server render, or jsdom without `canvas`) every width is 0, so
  `lineWidth` never leaves 0 and the space before every word is dropped: `<img src=x ...>` prints as `<imgsrc=x...>`.
  The plain-text path (`textLayerLines` string branch) returns the hard lines as typed, spaces kept.
- Introduced with the function itself: 5d0e05ae25 (PRICETAG-COMBO-FORMAT S3), merged in #2180 (5e97671eea,
  5 Nov 2026). Latent wherever `canvas` is installed; any run with no measure shows it (`canvasMeasure` also
  returns null when `document` is undefined). The print page itself is `'use client'` and draws in Chromium, which
  has a canvas, so no printed tag is known to be affected (UNVERIFIED against a server-rendered first paint).

Verdict: the CODE is wrong, the test is right. Escaped text must keep its spaces with or without a measure.

## Architecture

Layer: frontend lib (`lib/dealer-kit/text-layout.ts`, shared by the Konva canvas and the print page). Mechanism: the
"line has started" test in `richLayerLines` reads whether the line holds pieces (`line.length > 0`) instead of
whether it has width. With a measure the two are the same (every non-empty piece has width), so measured layouts do
not change. No new classes, no new module.

## Change

1. `text-layout.ts` `richLayerLines`: the space before a word group joins the line whenever the line already holds
   a piece (measured or not); the wrap/cut decisions stay gated on `measurable` as today.

## Tests

- Red (new, deterministic on any machine):
  - `lib/dealer-kit/text-lines.no-measure.test.ts`: `textLayerLines(props, parseRichText(...), w, h, null)` keeps
    the spaces between words and across runs (bold + plain).
  - `TagSheetRenderer.rich-text.no-canvas.test.tsx`: the AC-17 escaped `<img onerror>` string with
    `HTMLCanvasElement.prototype.getContext` returning null (the census environment) prints with its spaces, and
    still creates no img element and no handler attribute.
- Existing AC-17 test stays unchanged (security assertion untouched).
- Kill: revert the fix, both new files and the AC-17 test (with `canvas` hidden) go red; restore.
- Green set: every TagSheetRenderer / rich-text / text-layout test file plus the census set
  `scripts/source-guard-tests.sh` selects.

## Standing rules

No user-visible change where a canvas exists (the print page in Chromium, the designer canvas). Of the owner's
checklist only "Formatted text ... prints exactly as it shows on screen" touches this, and the fix keeps it so.
guide: n/a (no user-visible change).
