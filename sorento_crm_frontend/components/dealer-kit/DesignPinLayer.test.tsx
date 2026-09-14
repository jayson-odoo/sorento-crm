/**
 * Placing a pin on the design (r9 S2/D5, AC-S2-1 + AC-S2-2).
 *
 * There is no "Request changes" mode to turn on first (D): on a design waiting
 * for the salesperson, a click on a tag IS the change request. A click drops a
 * POINT pin (w = h = 0), a drag draws a box, and either opens the comment box
 * straight away. Escape or an empty comment throws the pin away rather than
 * leaving an unlabelled dot on somebody else's design.
 *
 * The fractions are the load-bearing part: a pin is stored as a fraction of ITS
 * TAG, never as a spot on the page, which is the only reason re-arranging the
 * sheet or zooming cannot move a comment off the thing it was pointing at.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

import DesignPinLayer from './DesignPinLayer';
import type { ReviewComment, DraftPin } from '@/lib/dealer-kit/review-comments';

const LINE = 'line-1';

const DOC = {
  kind: 'tag_sheet',
  imposition: { page_width_mm: 210, page_height_mm: 297 },
  sheets: [
    {
      id: 'sheet-1',
      tags: [
        {
          id: 'tag-1',
          request_line_id: LINE,
          x_mm: 20,
          y_mm: 30,
          width_mm: 80,
          height_mm: 40,
          layers: [],
        },
      ],
    },
  ],
} as never;

function comment(overrides: Partial<ReviewComment> = {}): ReviewComment {
  return {
    id: 'comment-1',
    request_id: 'req-1',
    line_id: LINE,
    round: 1,
    x: 0.5,
    y: 0.5,
    w: 0,
    h: 0,
    body: 'Make the price bigger',
    author_name: 'ZZT Sales Sam',
    created_at: '2026-09-14T00:00:00Z',
    resolved_at: null,
    resolved_by_name: null,
    ...overrides,
  };
}

/**
 * The tag hit area, with a real box: jsdom reports 0 for every rect, and the
 * fraction maths divides by the width.
 */
function hitArea(lineId = LINE) {
  const node = screen.getByTestId(`pin-hit-${lineId}`);
  node.getBoundingClientRect = () =>
    ({ left: 100, top: 200, width: 200, height: 100, right: 300, bottom: 300 }) as DOMRect;
  return node;
}

function renderLayer(props: Partial<React.ComponentProps<typeof DesignPinLayer>> = {}) {
  const onPlace = vi.fn();
  const onRemoveDraft = vi.fn();
  const result = render(
    <DesignPinLayer
      doc={DOC}
      sheetIndex={0}
      scale={1}
      comments={[]}
      drafts={[]}
      canPlace
      onPlace={onPlace}
      onRemoveDraft={onRemoveDraft}
      {...props}
    />,
  );
  return { ...result, onPlace, onRemoveDraft };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('placing a pin (AC-S2-1)', () => {
  it('the tag hit area has a hover affordance, not just the crosshair cursor (review-round leftover R8)', () => {
    renderLayer();
    const area = hitArea();

    expect(area.className).toContain('cursor-crosshair');
    expect(area.className).toMatch(/hover:(ring|outline)/);
  });

  it('a click drops a point pin and opens the comment box', () => {
    const { onPlace } = renderLayer();
    const area = hitArea();

    fireEvent.pointerDown(area, { clientX: 150, clientY: 250 });
    fireEvent.pointerUp(area, { clientX: 150, clientY: 250 });

    expect(screen.getByTestId('pin-comment-editor')).toBeInTheDocument();
    expect(onPlace).not.toHaveBeenCalled();

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'Make the price bigger' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    expect(onPlace).toHaveBeenCalledTimes(1);
    expect(onPlace).toHaveBeenCalledWith({
      line_id: LINE,
      placed_tag_id: 'tag-1',
      x: 0.25,
      y: 0.5,
      w: 0,
      h: 0,
      body: 'Make the price bigger',
    });
  });

  it('a drag draws a box whose corner is where the pointer went down', () => {
    const { onPlace } = renderLayer();
    const area = hitArea();

    fireEvent.pointerDown(area, { clientX: 150, clientY: 250 });
    fireEvent.pointerMove(area, { clientX: 250, clientY: 280 });
    fireEvent.pointerUp(area, { clientX: 250, clientY: 280 });
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'This block' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    const placed = onPlace.mock.calls[0][0];
    expect(placed.x).toBeCloseTo(0.25, 5);
    expect(placed.y).toBeCloseTo(0.5, 5);
    expect(placed.w).toBeCloseTo(0.5, 5);
    expect(placed.h).toBeCloseTo(0.3, 5);
    for (const value of [placed.x, placed.y, placed.w, placed.h]) {
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThanOrEqual(1);
    }
  });

  it('a drag past the tag edge clamps to the tag rather than spilling', () => {
    const { onPlace } = renderLayer();
    const area = hitArea();

    fireEvent.pointerDown(area, { clientX: 250, clientY: 250 });
    fireEvent.pointerMove(area, { clientX: 900, clientY: 900 });
    fireEvent.pointerUp(area, { clientX: 900, clientY: 900 });
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Everything' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    const placed = onPlace.mock.calls[0][0];
    expect(placed.x + placed.w).toBeLessThanOrEqual(1);
    expect(placed.y + placed.h).toBeLessThanOrEqual(1);
  });

  it('a drag that leaves the tag still finishes the pin', () => {
    // The rail the salesperson drags a box with is the tag's own hit area, and
    // the move/up handlers are on it - so a drag that ends anywhere else
    // (which a box around the whole tag always does, and a fast drag usually
    // does) never gets its pointerup. The pin is left half-placed: no box, no
    // comment box, and the next click starts again. A real browser solves this
    // with pointer capture, which jsdom does not implement; window listeners
    // while placing is the shape that works in both.
    const { onPlace } = renderLayer();
    const area = hitArea();

    fireEvent.pointerDown(area, { clientX: 150, clientY: 250 });
    fireEvent.pointerMove(window, { clientX: 400, clientY: 500 });
    fireEvent.pointerUp(window, { clientX: 400, clientY: 500 });

    const editor = screen.getByTestId('pin-comment-editor');
    fireEvent.change(within(editor).getByRole('textbox'), {
      target: { value: 'This whole corner' },
    });
    fireEvent.click(within(editor).getByRole('button', { name: 'Add' }));

    const placed = onPlace.mock.calls[0][0];
    expect(placed.w).toBeGreaterThan(0);
    expect(placed.h).toBeGreaterThan(0);
  });

  it('Escape throws the pin away', () => {
    const { onPlace } = renderLayer();
    const area = hitArea();
    fireEvent.pointerDown(area, { clientX: 150, clientY: 250 });
    fireEvent.pointerUp(area, { clientX: 150, clientY: 250 });

    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' });

    expect(screen.queryByTestId('pin-comment-editor')).toBeNull();
    expect(onPlace).not.toHaveBeenCalled();
  });

  it('an empty comment cannot be added', () => {
    const { onPlace } = renderLayer();
    const area = hitArea();
    fireEvent.pointerDown(area, { clientX: 150, clientY: 250 });
    fireEvent.pointerUp(area, { clientX: 150, clientY: 250 });

    expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled();

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onPlace).not.toHaveBeenCalled();
  });

  it('nobody can place a pin on a design that is not waiting on them', () => {
    renderLayer({ canPlace: false });

    expect(screen.queryByTestId(`pin-hit-${LINE}`)).toBeNull();
  });
});

describe('reading the pins that exist (AC-S2-2)', () => {
  it('numbers sent comments first and continues the sequence into the drafts', () => {
    const drafts: DraftPin[] = [
      { key: 'draft-a', line_id: LINE, x: 0.1, y: 0.1, w: 0, h: 0, body: 'New one' },
    ];
    renderLayer({ comments: [comment()], drafts });

    expect(screen.getByLabelText('Change request 1')).toBeInTheDocument();
    expect(screen.getByLabelText('Change request 2')).toBeInTheDocument();
  });

  it('opens a sent comment on click and does not offer to delete it', () => {
    renderLayer({ comments: [comment()] });

    fireEvent.click(screen.getByLabelText('Change request 1'));

    expect(screen.getByText('Make the price bigger')).toBeInTheDocument();
    expect(screen.getByText('Round 1')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Delete/ })).toBeNull();
  });

  it('a draft can be deleted before it is sent', () => {
    const drafts: DraftPin[] = [
      { key: 'draft-a', line_id: LINE, x: 0.1, y: 0.1, w: 0, h: 0, body: 'New one' },
    ];
    const { onRemoveDraft } = renderLayer({ drafts });

    fireEvent.click(screen.getByLabelText('Change request 1'));
    expect(screen.getByText('Not sent yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Delete/ }));

    expect(onRemoveDraft).toHaveBeenCalledWith('draft-a');
  });

  it('a resolved comment says so rather than disappearing', () => {
    renderLayer({
      comments: [comment({ resolved_at: '2026-09-14T02:00:00Z', resolved_by_name: 'Mei' })],
    });

    fireEvent.click(screen.getByLabelText('Change request 1'));

    expect(screen.getByText(/Done/)).toBeInTheDocument();
  });

  it('an earlier round greys out once a new proof has been sent (D6)', () => {
    // Round 1's pins stay on the design so round 2 is read against what was
    // already asked for - grey whether or not anybody ticked them Done,
    // because they are not what this round is waiting on.
    renderLayer({
      comments: [
        comment({ id: 'old', round: 1, body: 'Asked for last time' }),
        comment({ id: 'new', round: 2, body: 'Asking now' }),
      ],
      currentRound: 2,
    });

    const earlier = screen.getByLabelText('Change request 1');
    const current = screen.getByLabelText('Change request 2');
    expect(earlier.className).toContain('bg-muted-foreground');
    expect(current.className).toContain('bg-primary');
    expect(current.className).not.toContain('bg-muted-foreground');
  });

  it('the current round stays blue while it is still open', () => {
    renderLayer({ comments: [comment({ round: 1 })], currentRound: 1 });

    expect(screen.getByLabelText('Change request 1').className).toContain(
      'bg-primary',
    );
  });

  it('with no round given, only Done greys a pin', () => {
    // The portal read view passes no round on a design nobody is reviewing;
    // an undefined round must not grey the whole history.
    renderLayer({ comments: [comment({ round: 1 })] });

    expect(screen.getByLabelText('Change request 1').className).toContain(
      'bg-primary',
    );
  });

  it('a general comment carries no marker at all', () => {
    renderLayer({
      comments: [comment({ line_id: null, x: null, y: null, w: null, h: null })],
    });

    expect(screen.queryByLabelText(/Change request/)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Owner test round, finding 1 - a pin anchors to ONE placed copy, not every
// copy of the line, once a sheet prints that line more than once.
// ---------------------------------------------------------------------------

/** Two copies of the SAME line on one sheet - what "Apply to all lines" or a
 * quantity > 1 produces. Different `PlacedTag.id`s, same `request_line_id`. */
const TWO_COPY_DOC = {
  kind: 'tag_sheet',
  imposition: { page_width_mm: 210, page_height_mm: 297 },
  sheets: [
    {
      id: 'sheet-1',
      tags: [
        {
          id: 'tag-a',
          template_id: 'tmpl-1',
          request_line_id: LINE,
          x_mm: 0,
          y_mm: 0,
          width_mm: 80,
          height_mm: 40,
          layers: [],
        },
        {
          id: 'tag-b',
          template_id: 'tmpl-1',
          request_line_id: LINE,
          x_mm: 100,
          y_mm: 0,
          width_mm: 80,
          height_mm: 40,
          layers: [],
        },
      ],
    },
  ],
} as never;

function twoCopyHitAreas() {
  const nodes = screen.getAllByTestId(`pin-hit-${LINE}`);
  nodes[0].getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 200, height: 100, right: 200, bottom: 100 }) as DOMRect;
  nodes[1].getBoundingClientRect = () =>
    ({ left: 300, top: 0, width: 200, height: 100, right: 500, bottom: 100 }) as DOMRect;
  return nodes;
}

describe('a pin anchors to the placed copy that was clicked (owner round finding 1)', () => {
  it('placing a pin on the SECOND copy sends that copy id as placed_tag_id', () => {
    const { onPlace } = renderLayer({ doc: TWO_COPY_DOC });
    const [, second] = twoCopyHitAreas();

    fireEvent.pointerDown(second, { clientX: 350, clientY: 50 });
    fireEvent.pointerUp(second, { clientX: 350, clientY: 50 });
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'Fix this one' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    expect(onPlace).toHaveBeenCalledWith(
      expect.objectContaining({ line_id: LINE, placed_tag_id: 'tag-b' }),
    );
  });

  it('a sent pin with placed_tag_id draws on that copy only, the sibling stays empty', () => {
    renderLayer({
      doc: TWO_COPY_DOC,
      comments: [comment({ placed_tag_id: 'tag-a' } as never)],
    });

    // One marker only - not one per copy of the line.
    expect(screen.getAllByTestId('pin-comment-1')).toHaveLength(1);
  });

  it('placed_tag_id null falls back to every copy of the line', () => {
    renderLayer({
      doc: TWO_COPY_DOC,
      comments: [comment({ placed_tag_id: null } as never)],
    });

    expect(screen.getAllByTestId('pin-comment-1')).toHaveLength(2);
  });

  it('a placed_tag_id no copy carries any more (re-arranged away) falls back to every copy', () => {
    renderLayer({
      doc: TWO_COPY_DOC,
      comments: [comment({ placed_tag_id: 'tag-gone' } as never)],
    });

    expect(screen.getAllByTestId('pin-comment-1')).toHaveLength(2);
  });
});
