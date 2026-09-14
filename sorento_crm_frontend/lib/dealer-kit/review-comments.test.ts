/**
 * Pin geometry and numbering (r9 S2/D4-D6, AC-S2-4).
 *
 * A pin is stored as a FRACTION of its tag box. AC-S2-4 is "after zooming,
 * paging sheets and re-arranging tags in Arrange, each pin sits on the same
 * spot of its tag" - which is a statement about arithmetic, so it is asserted
 * as arithmetic: the same fraction resolves to the same MILLIMETRE point on the
 * sheet at every scale, and follows the tag when Arrange moves it.
 *
 * The numbering matters for the same reason a footnote number does: the rail
 * and the marker have to say the same thing, and a second round must not
 * renumber the first under the reader.
 */
import { describe, it, expect } from 'vitest';

import {
  canvasPinsForLine,
  clampFraction,
  latestRound,
  numberedPins,
  openComments,
  openCountByLine,
  tagRectsForSheet,
  type DraftPin,
  type ReviewComment,
} from './review-comments';
import type { TagSheetDoc } from './tag-template-types';

const PX_PER_MM = 96 / 25.4;

function doc(tagX = 20, tagY = 30): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: { page_width_mm: 210, page_height_mm: 297 },
    sheets: [
      {
        id: 'sheet-1',
        tags: [
          {
            id: 'tag-1',
            request_line_id: 'line-1',
            x_mm: tagX,
            y_mm: tagY,
            width_mm: 80,
            height_mm: 40,
            layers: [],
          },
          {
            id: 'tag-2',
            request_line_id: 'line-2',
            x_mm: 110,
            y_mm: 30,
            width_mm: 80,
            height_mm: 40,
            layers: [],
          },
        ],
      },
    ],
  } as unknown as TagSheetDoc;
}

function comment(overrides: Partial<ReviewComment> = {}): ReviewComment {
  return {
    id: 'c1',
    request_id: 'req-1',
    line_id: 'line-1',
    round: 1,
    x: 0.25,
    y: 0.5,
    w: 0,
    h: 0,
    body: 'Bigger price',
    author_name: 'Sam',
    created_at: '2026-09-14T00:00:00Z',
    resolved_at: null,
    resolved_by_name: null,
    ...overrides,
  };
}

describe('tagRectsForSheet (AC-S2-4)', () => {
  it('places a tag at its millimetre position scaled to pixels', () => {
    const [first] = tagRectsForSheet(doc(), 0, 1);

    expect(first.tagId).toBe('tag-1');
    expect(first.lineId).toBe('line-1');
    expect(first.left).toBeCloseTo(20 * PX_PER_MM, 5);
    expect(first.top).toBeCloseTo(30 * PX_PER_MM, 5);
    expect(first.width).toBeCloseTo(80 * PX_PER_MM, 5);
  });

  it('the same fraction lands on the same MILLIMETRE point at two scales', () => {
    const fraction = { x: 0.25, y: 0.75 };

    const point = (scale: number) => {
      const [rect] = tagRectsForSheet(doc(), 0, scale);
      return {
        xMm: (rect.left + fraction.x * rect.width) / (PX_PER_MM * scale),
        yMm: (rect.top + fraction.y * rect.height) / (PX_PER_MM * scale),
      };
    };

    const small = point(0.35);
    const large = point(2.4);
    expect(small.xMm).toBeCloseTo(large.xMm, 5);
    expect(small.yMm).toBeCloseTo(large.yMm, 5);
    // And it is the point the reader pointed at: 25% across an 80mm tag that
    // starts at 20mm is 40mm from the page edge.
    expect(small.xMm).toBeCloseTo(40, 5);
  });

  it('the pin follows the tag when Arrange moves it', () => {
    const before = tagRectsForSheet(doc(20, 30), 0, 1)[0];
    const after = tagRectsForSheet(doc(120, 200), 0, 1)[0];

    const offsetBefore = 0.25 * before.width;
    const offsetAfter = 0.25 * after.width;
    expect(offsetBefore).toBeCloseTo(offsetAfter, 5);
    expect(after.left - before.left).toBeCloseTo(100 * PX_PER_MM, 5);
  });

  it('a sheet index past the end is no tags rather than a crash', () => {
    expect(tagRectsForSheet(doc(), 9, 1)).toEqual([]);
    expect(tagRectsForSheet(null, 0, 1)).toEqual([]);
  });
});

describe('clampFraction', () => {
  it('keeps a pin inside its tag', () => {
    expect(clampFraction(-0.4)).toBe(0);
    expect(clampFraction(1.9)).toBe(1);
    expect(clampFraction(0.42)).toBe(0.42);
  });
});

describe('numbering', () => {
  it('numbers sent comments in order and continues into the drafts', () => {
    const comments = [comment({ id: 'c1' }), comment({ id: 'c2' })];
    const drafts: DraftPin[] = [
      { key: 'd1', line_id: 'line-1', x: 0.1, y: 0.1, w: 0, h: 0, body: 'New' },
    ];

    const { commentNumbers, draftNumbers } = numberedPins(comments, drafts);

    expect(commentNumbers.get('c1')).toBe(1);
    expect(commentNumbers.get('c2')).toBe(2);
    expect(draftNumbers.get('d1')).toBe(3);
  });

  it('a general comment takes no number - it has no marker to wear it', () => {
    const comments = [
      comment({ id: 'general', line_id: null, x: null, y: null }),
      comment({ id: 'pinned' }),
    ];

    const { commentNumbers } = numberedPins(comments, []);

    expect(commentNumbers.has('general')).toBe(false);
    expect(commentNumbers.get('pinned')).toBe(1);
  });

  it('a resolved comment keeps its number so round one does not renumber', () => {
    const comments = [
      comment({ id: 'c1', resolved_at: '2026-09-14T01:00:00Z' }),
      comment({ id: 'c2', round: 2 }),
    ];

    const { commentNumbers } = numberedPins(comments, []);

    expect(commentNumbers.get('c1')).toBe(1);
    expect(commentNumbers.get('c2')).toBe(2);
  });
});

describe('open counts (AC-S2-6 rail badge, AC-S2-7 CTA label)', () => {
  it('open means nobody has ticked it Done', () => {
    const rows = [
      comment({ id: 'c1' }),
      comment({ id: 'c2', resolved_at: '2026-09-14T01:00:00Z' }),
    ];

    expect(openComments(rows).map((row) => row.id)).toEqual(['c1']);
  });

  it('counts open pins per line, ignoring general comments', () => {
    const rows = [
      comment({ id: 'c1', line_id: 'line-1' }),
      comment({ id: 'c2', line_id: 'line-1' }),
      comment({ id: 'c3', line_id: 'line-2' }),
      comment({ id: 'c4', line_id: 'line-2', resolved_at: '2026-09-14T01:00:00Z' }),
      comment({ id: 'c5', line_id: null }),
    ];

    const counts = openCountByLine(rows);

    expect(counts.get('line-1')).toBe(2);
    expect(counts.get('line-2')).toBe(1);
    expect(counts.size).toBe(2);
  });

  it('the latest round is the highest any comment carries', () => {
    expect(latestRound([])).toBe(0);
    expect(latestRound([comment({ round: 1 }), comment({ round: 3 })])).toBe(3);
  });
});

describe('canvasPinsForLine (AC-S2-6)', () => {
  it('gives the designer this line pins only, numbered as everywhere else', () => {
    const rows = [
      comment({ id: 'c1', line_id: 'line-1' }),
      comment({ id: 'c2', line_id: 'line-2' }),
      comment({ id: 'c3', line_id: null, x: null, y: null }),
    ];

    const pins = canvasPinsForLine(rows, 'line-2');

    expect(pins.map((pin) => pin.id)).toEqual(['c2']);
    expect(pins[0].number).toBe(2);
    expect(pins[0].x).toBeCloseTo(0.25, 5);
    expect(pins[0].resolved).toBe(false);
    expect(pins[0].caption).toBe('Round 1');
  });

  it('says Done in the caption once it is resolved', () => {
    const pins = canvasPinsForLine(
      [comment({ resolved_at: '2026-09-14T01:00:00Z' })],
      'line-1',
    );

    expect(pins[0].resolved).toBe(true);
    expect(pins[0].caption).toContain('Done');
  });

  it('no selected line is no pins', () => {
    expect(canvasPinsForLine([comment()], null)).toEqual([]);
  });
});
