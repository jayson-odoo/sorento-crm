/**
 * Doors and windows, written before the implementation.
 *
 * An opening is not a product. It has no price, it never appears on a quote,
 * and it cannot exist anywhere except inside a wall - which is why it is
 * modelled as an offset ALONG a wall rather than as a position in the room. A
 * wall that moves takes its door with it, and a wall that shortens either
 * carries its door inward or refuses to hold it at all.
 *
 * The planner we studied works the same way: click a wall, stamp a door on it,
 * then slide it along with live distances to each end.
 */
import { describe, expect, it } from 'vitest';

import {
  DEFAULT_DOOR,
  DEFAULT_WINDOW,
  fitOpening,
  openingEdgeGaps,
  openingSpans,
  wallPanels,
  type Opening,
} from './roomOpenings';

function door(overrides: Partial<Opening> = {}): Opening {
  return {
    id: 'a',
    kind: 'door',
    wallIndex: 0,
    offsetMm: 1500,
    widthMm: 900,
    heightMm: 2100,
    sillMm: 0,
    ...overrides,
  };
}

describe('fitOpening', () => {
  it('leaves an opening that already fits exactly where it is', () => {
    expect(fitOpening(door(), 4000)).toEqual(door());
  });

  it('slides an opening inward rather than letting it hang off the end', () => {
    // Half a metre past the end of a 4m wall: a door drawn there is a door that
    // cannot be installed.
    const fitted = fitOpening(door({ offsetMm: 3900 }), 4000);

    expect(fitted!.offsetMm).toBe(4000 - 450);
  });

  it('slides an opening off the near end back in too', () => {
    const fitted = fitOpening(door({ offsetMm: 100 }), 4000);

    expect(fitted!.offsetMm).toBe(450);
  });

  it('refuses an opening wider than the wall instead of shrinking it', () => {
    // Silently narrowing a 900 door to fit a 700 wall would put a measurement
    // in the drawing that nobody chose.
    expect(fitOpening(door({ widthMm: 900 }), 700)).toBeNull();
  });

  it('refuses a wall of no length', () => {
    expect(fitOpening(door(), 0)).toBeNull();
  });
});

describe('openingSpans', () => {
  it('gives the whole wall when nothing is cut into it', () => {
    expect(openingSpans(4000, [])).toEqual([{ start: 0, end: 4000 }]);
  });

  it('splits the wall either side of one opening', () => {
    expect(openingSpans(4000, [door({ offsetMm: 2000, widthMm: 1000 })])).toEqual([
      { start: 0, end: 1500 },
      { start: 2500, end: 4000 },
    ]);
  });

  it('handles two openings in order, whatever order they were added in', () => {
    const spans = openingSpans(6000, [
      door({ id: 'b', offsetMm: 4500, widthMm: 1000 }),
      door({ id: 'a', offsetMm: 1500, widthMm: 1000 }),
    ]);

    expect(spans).toEqual([
      { start: 0, end: 1000 },
      { start: 2000, end: 4000 },
      { start: 5000, end: 6000 },
    ]);
  });

  it('drops a span of no width when an opening reaches the end of the wall', () => {
    const spans = openingSpans(4000, [door({ offsetMm: 3550, widthMm: 900 })]);

    expect(spans).toEqual([{ start: 0, end: 3100 }]);
  });

  it('merges overlapping openings rather than emitting a negative span', () => {
    const spans = openingSpans(4000, [
      door({ id: 'a', offsetMm: 1500, widthMm: 1000 }),
      door({ id: 'b', offsetMm: 1800, widthMm: 1000 }),
    ]);

    expect(spans).toEqual([
      { start: 0, end: 1000 },
      { start: 2300, end: 4000 },
    ]);
  });
});

describe('wallPanels', () => {
  it('puts nothing under a door and a lintel above it', () => {
    expect(wallPanels(door(), 2700)).toEqual([{ bottom: 2100, top: 2700 }]);
  });

  it('puts a sill under a window and a lintel above it', () => {
    const window = door({ kind: 'window', sillMm: 900, heightMm: 1200 });

    expect(wallPanels(window, 2700)).toEqual([
      { bottom: 0, top: 900 },
      { bottom: 2100, top: 2700 },
    ]);
  });

  it('emits no lintel when the opening reaches the ceiling', () => {
    const full = door({ heightMm: 2700 });

    expect(wallPanels(full, 2700)).toEqual([]);
  });

  it('treats an opening taller than the wall as reaching the ceiling', () => {
    expect(wallPanels(door({ heightMm: 3200 }), 2700)).toEqual([]);
  });
});

describe('openingEdgeGaps', () => {
  it('measures to each end of the wall', () => {
    const gaps = openingEdgeGaps(door({ offsetMm: 1500, widthMm: 900 }), 4000, []);

    // 1500 - 450 = 1050 back, 4000 - 1950 = 2050 on.
    expect(gaps).toEqual({ before: 1050, after: 2050 });
  });

  it('measures to a neighbouring opening rather than past it', () => {
    const neighbour = door({ id: 'b', offsetMm: 3000, widthMm: 600 });
    const gaps = openingEdgeGaps(door({ offsetMm: 1500, widthMm: 900 }), 4000, [neighbour]);

    // 2700 - 1950 = 750 to the neighbour.
    expect(gaps).toEqual({ before: 1050, after: 750 });
  });

  it('ignores an opening on a different wall', () => {
    const elsewhere = door({ id: 'b', wallIndex: 2, offsetMm: 2000, widthMm: 900 });
    const gaps = openingEdgeGaps(door({ offsetMm: 1500, widthMm: 900 }), 4000, [elsewhere]);

    expect(gaps).toEqual({ before: 1050, after: 2050 });
  });

  it('never reports a negative gap', () => {
    const overlapping = door({ id: 'b', offsetMm: 1600, widthMm: 900 });
    const gaps = openingEdgeGaps(door({ offsetMm: 1500, widthMm: 900 }), 4000, [overlapping]);

    expect(gaps.after).toBe(0);
  });
});

describe('defaults', () => {
  it('are the sizes somebody would otherwise have to look up', () => {
    // A standard single leaf door and a standard window, so stamping one and
    // moving on is the normal case and typing sizes is the exception.
    expect(DEFAULT_DOOR.widthMm).toBe(900);
    expect(DEFAULT_DOOR.heightMm).toBe(2100);
    expect(DEFAULT_DOOR.sillMm).toBe(0);
    expect(DEFAULT_WINDOW.sillMm).toBeGreaterThan(0);
  });
});
