/**
 * PRICETAG-DESIGNER-FEEDBACK AC-9.1 / AC-9.2: during a crop session the picture stays put and only
 * the crop window moves (owner, 14 Nov: the photo "shakes" and zooms while a handle is dragged,
 * and panning the window slides the picture the other way).
 *
 * Written test-FIRST against a NEW pure helper the coder adds to `image-crop.ts`:
 *
 *   cropSessionLayout(
 *     session: CropRect | null | undefined,   // the crop the session STARTED from (fixed)
 *     cropRect: CropRect | null | undefined,  // the in-flight crop
 *     natural: { width: number; height: number },
 *     fit: 'cover' | 'contain' | 'stretch',
 *     w: number,
 *     h: number,
 *   ): { window: Rect; source: Rect }
 *
 * `source` is `cropOverlayLayout(session, ...).source` and never depends on `cropRect`;
 * `window` is `cropRect` mapped onto that fixed source. With `cropRect` equal to `session` the
 * result equals `cropOverlayLayout(session, ...)`, so entering crop mode looks exactly as today.
 */
import { describe, expect, it } from 'vitest';

import * as imageCrop from './image-crop';
import { CROP_HANDLE_ANCHORS, cropOverlayLayout, cropRectFromDrag, panCropRect, type CropRect } from './image-crop';

type Rect = { x: number; y: number; width: number; height: number };
type SessionLayout = (
  session: CropRect | null | undefined,
  cropRect: CropRect | null | undefined,
  natural: { width: number; height: number },
  fit: 'cover' | 'contain' | 'stretch',
  w: number,
  h: number,
) => { window: Rect; source: Rect };

function sessionLayout(): SessionLayout {
  const fn = (imageCrop as unknown as { cropSessionLayout?: SessionLayout }).cropSessionLayout;
  expect(typeof fn, 'image-crop.ts exports cropSessionLayout').toBe('function');
  return fn!;
}

const NATURAL = { width: 300, height: 150 };
const anchor = (name: string) => CROP_HANDLE_ANCHORS.find((a) => a.name === name)!;

function expectRectClose(actual: Rect, expected: Rect) {
  expect(actual.x).toBeCloseTo(expected.x, 6);
  expect(actual.y).toBeCloseTo(expected.y, 6);
  expect(actual.width).toBeCloseTo(expected.width, 6);
  expect(actual.height).toBeCloseTo(expected.height, 6);
}

for (const fit of ['contain', 'cover', 'stretch'] as const) {
  describe(`cropSessionLayout, fit ${fit}`, () => {
    // A 1:1 box over a 2:1 source, so contain and cover differ.
    const W = 60;
    const H = 60;
    const session: CropRect = { x: 0.1, y: 0.2, width: 0.5, height: 0.6 };

    it('AC-9.1: with the crop at its session start it equals today\'s overlay layout', () => {
      const layout = sessionLayout()(session, session, NATURAL, fit, W, H);
      const today = cropOverlayLayout(session, NATURAL, fit, W, H);
      expectRectClose(layout.window, today.window);
      expectRectClose(layout.source, today.source);
    });

    it('AC-9.1: the source picture keeps the same position and scale for every crop in the session', () => {
      const start = sessionLayout()(session, session, NATURAL, fit, W, H).source;
      for (const next of [
        { x: 0.1, y: 0.2, width: 0.3, height: 0.6 },
        { x: 0.25, y: 0.3, width: 0.2, height: 0.2 },
        { x: 0, y: 0, width: 1, height: 1 },
      ]) {
        expectRectClose(sessionLayout()(session, next, NATURAL, fit, W, H).source, start);
      }
    });

    it('AC-9.1: the window is the crop rect laid on that fixed source', () => {
      const next = { x: 0.25, y: 0.3, width: 0.2, height: 0.4 };
      const { source, window } = sessionLayout()(session, next, NATURAL, fit, W, H);
      expectRectClose(window, {
        x: source.x + next.x * source.width,
        y: source.y + next.y * source.height,
        width: next.width * source.width,
        height: next.height * source.height,
      });
    });

    it('AC-9.1: a handle dragged by (dx, dy) px stays under the pointer', () => {
      const start = sessionLayout()(session, session, NATURAL, fit, W, H);
      const dx = -9;
      const dy = 6;
      const handle = anchor('bottom-right');
      const next = cropRectFromDrag(session, handle, dx / start.source.width, dy / start.source.height);
      const moved = sessionLayout()(session, next, NATURAL, fit, W, H).window;
      expect(moved.x + moved.width).toBeCloseTo(start.window.x + start.window.width + dx, 6);
      expect(moved.y + moved.height).toBeCloseTo(start.window.y + start.window.height + dy, 6);
      // The opposite corner did not move.
      expect(moved.x).toBeCloseTo(start.window.x, 6);
      expect(moved.y).toBeCloseTo(start.window.y, 6);
    });

    it('AC-9.2: dragging the window right by d moves the crop right and the window right by d; the picture stays', () => {
      const start = sessionLayout()(session, session, NATURAL, fit, W, H);
      const d = 6;
      const next = panCropRect(session, d / start.source.width, 0);
      expect(next.x).toBeGreaterThan(session.x);
      const moved = sessionLayout()(session, next, NATURAL, fit, W, H);
      expect(moved.window.x).toBeCloseTo(start.window.x + d, 6);
      expect(moved.window.y).toBeCloseTo(start.window.y, 6);
      expectRectClose(moved.source, start.source);
    });
  });
}
