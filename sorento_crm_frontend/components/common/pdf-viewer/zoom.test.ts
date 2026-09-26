/**
 * Zoom math for the PDF viewer: the point under the cursor stays put across a zoom.
 */
import { describe, expect, it } from 'vitest';

import {
  anchoredScroll,
  captureAnchor,
  clampZoom,
  type PageBox,
  wheelZoomFactor,
  ZOOM_MAX,
  ZOOM_MIN,
} from './zoom';

const PADDING = 8;
const GAP = 8;

/** A column of equal pages at `scale`, laid out the way the viewer lays them out. */
function layout(scale: number, count = 3, viewWidth = 700): PageBox[] {
  const width = 600 * scale;
  const height = 800 * scale;
  // Centred in a column at least as wide as the view.
  const column = Math.max(viewWidth - 2 * PADDING, width);
  const left = PADDING + (column - width) / 2;
  return Array.from({ length: count }, (_, i) => ({
    left,
    top: PADDING + i * (height + GAP),
    width,
    height,
  }));
}

/** The document point (page index + page units at scale 1) under a cursor. */
function pointUnder(pages: PageBox[], scroll: { left: number; top: number }, cursor: { x: number; y: number }, scale: number) {
  const x = scroll.left + cursor.x;
  const y = scroll.top + cursor.y;
  const index = pages.findIndex((p) => y < p.top + p.height);
  const page = pages[index];
  return { index, u: (x - page.left) / scale, v: (y - page.top) / scale };
}

describe('clampZoom', () => {
  it('keeps the zoom inside its bounds and rounds it to a whole percent', () => {
    expect(clampZoom(0.01)).toBe(ZOOM_MIN);
    expect(clampZoom(99)).toBe(ZOOM_MAX);
    expect(clampZoom(1.23456)).toBe(1.23);
  });
});

describe('captureAnchor', () => {
  it('records the point as a fraction of the page under it', () => {
    const pages = layout(1);
    // Page 2 starts at 8 + 808 = 816; its left edge is 8 + (684 - 600) / 2 = 50.
    const anchor = captureAnchor(pages, { x: 50 + 300, y: 816 + 200 });
    expect(anchor).toEqual({ index: 1, fx: 0.5, fy: 0.25 });
  });

  it('gives a point in the gap between pages to the page below it', () => {
    const pages = layout(1);
    const anchor = captureAnchor(pages, { x: 50, y: 812 });
    expect(anchor?.index).toBe(1);
    expect(anchor?.fy).toBeLessThan(0);
  });

  it('gives a point past the last page to the last page', () => {
    const pages = layout(1);
    const anchor = captureAnchor(pages, { x: 50, y: 5000 });
    expect(anchor?.index).toBe(2);
    expect(anchor?.fy).toBeGreaterThan(1);
  });

  it('has nothing to anchor to when there are no pages', () => {
    expect(captureAnchor([], { x: 1, y: 1 })).toBeNull();
  });
});

describe('anchoredScroll', () => {
  function zoomAround(from: number, to: number, scroll: { left: number; top: number }) {
    const cursor = { x: 420, y: 230 };
    const before = layout(from);
    const was = pointUnder(before, scroll, cursor, from);

    const anchor = captureAnchor(before, { x: scroll.left + cursor.x, y: scroll.top + cursor.y });
    const after = layout(to);
    const next = anchoredScroll(after[anchor!.index], anchor!, cursor);
    return { was, now: pointUnder(after, next, cursor, to) };
  }

  it.each([
    [1, 2],
    [0.8, 3.1],
    [1.25, 1.5],
  ])('zooming in %s -> %s keeps the point under the cursor where it was', (from, to) => {
    const { was, now } = zoomAround(from, to, { left: from > 1 ? 120 : 0, top: 900 });

    expect(now.index).toBe(was.index);
    expect(now.u).toBeCloseTo(was.u, 6);
    expect(now.v).toBeCloseTo(was.v, 6);
  });

  it.each([
    [2, 1],
    [2.5, 0.5],
  ])('zooming out %s -> %s keeps the line under the cursor where it was', (from, to) => {
    // Across, the page may now be narrower than the view and simply centres, so only the
    // vertical position can (and must) hold.
    const { was, now } = zoomAround(from, to, { left: 120, top: 2400 });

    expect(now.index).toBe(was.index);
    expect(now.v).toBeCloseTo(was.v, 6);
  });

  it('never asks for a negative scroll offset', () => {
    const pages = layout(1);
    const anchor = captureAnchor(pages, { x: 60, y: 20 })!;
    const next = anchoredScroll(layout(0.5)[0], anchor, { x: 600, y: 500 });
    expect(next.left).toBe(0);
    expect(next.top).toBe(0);
  });
});

describe('wheelZoomFactor', () => {
  it('zooms in on a wheel turned up, out on a wheel turned down, by the same amount', () => {
    const up = wheelZoomFactor(-100);
    const down = wheelZoomFactor(100);
    expect(up).toBeGreaterThan(1);
    expect(down).toBeLessThan(1);
    expect(up * down).toBeCloseTo(1, 10);
  });

  it('makes one mouse wheel notch about one toolbar step', () => {
    expect(wheelZoomFactor(-100)).toBeGreaterThan(1.15);
    expect(wheelZoomFactor(-100)).toBeLessThan(1.35);
  });

  it('turns many small pinch deltas into the same zoom as one large one', () => {
    let pinched = 1;
    for (let i = 0; i < 10; i += 1) pinched *= wheelZoomFactor(-10);
    expect(pinched).toBeCloseTo(wheelZoomFactor(-100), 10);
  });

  it('reads line-mode deltas (Firefox) as lines, not pixels', () => {
    // deltaMode 1: three lines for one notch.
    expect(wheelZoomFactor(-3, 1)).toBeCloseTo(wheelZoomFactor(-3 * 40), 10);
  });

  it('caps one event, so a flung wheel cannot jump across the whole range', () => {
    expect(wheelZoomFactor(-100000)).toBeLessThanOrEqual(2);
    expect(wheelZoomFactor(100000)).toBeGreaterThanOrEqual(0.5);
  });
});
