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
import { render, screen, fireEvent } from '@testing-library/react';

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

  it('a general comment carries no marker at all', () => {
    renderLayer({
      comments: [comment({ line_id: null, x: null, y: null, w: null, h: null })],
    });

    expect(screen.queryByLabelText(/Change request/)).toBeNull();
  });
});
