/**
 * AC-S9-4 (PLAN-price-tag-ai-extract-resolver.md D13): the review-pin popover
 * gains a Done/Reopen button ONLY when the caller hands `onReviewPinResolve`.
 * Every other mount point (the template editor, any read-only surface) never
 * passes it, so the popover has to stay exactly as it is today for them.
 *
 * Mocking boilerplate copied from `TagCanvasEditor.nudge.test.tsx` - Konva
 * does not run in jsdom.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultShapeProps } from '@/lib/dealer-kit/tag-template-types';
import type { CanvasReviewPin } from '@/lib/dealer-kit/review-comments';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    Stage: passthrough('stage'),
    Layer: passthrough('layer'),
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Circle: passthrough('circle'),
    Line: passthrough('line'),
    Transformer: passthrough('transformer'),
  };
});

vi.mock('./KonvaTagLayer', () => ({
  KonvaTagLayer: () => <div data-testid="layer-stand-in" />,
}));

vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => ({ failed: [] })),
  ensureSeedFontsLoaded: vi.fn(async () => {}),
  TAG_FONT_STYLESHEET: '',
  SEED_FONT_FAMILIES: [],
}));

vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
}));

vi.mock('../../services/tagDataService', () => ({
  productOptions: vi.fn(async () => []),
  productSetOptions: vi.fn(async () => []),
  listSpecKeys: vi.fn(async () => []),
  getProductTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
  getProductSetTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
}));

import { TagCanvasEditor } from './TagCanvasEditor';

function docWith(...layers: TagLayer[]): TagTemplateDoc {
  return { width_mm: 60, height_mm: 40, layers };
}

function shapeLayer(id: string): TagLayer {
  return {
    id,
    type: 'shape',
    x_mm: 10,
    y_mm: 10,
    width_mm: 20,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: defaultShapeProps(),
  };
}

const PIN: CanvasReviewPin = {
  id: 'comment-1',
  number: 1,
  x: 0.2,
  y: 0.3,
  w: 0,
  h: 0,
  body: 'Move the logo up',
  resolved: false,
  caption: 'Round 1',
};

describe('TagCanvasEditor review pin popover (AC-S9-1, AC-S9-4)', () => {
  it('renders no Done button when the caller gives no onReviewPinResolve', () => {
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('l1'))}
        onChange={vi.fn()}
        reviewPins={[PIN]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Change request 1' }));

    const popover = screen.getByRole('note');
    expect(within(popover).getByText('Move the logo up')).toBeInTheDocument();
    expect(within(popover).queryByRole('button', { name: /Done/ })).toBeNull();
    expect(within(popover).queryByRole('button', { name: /Reopen/ })).toBeNull();
  });

  it('AC-S9-1: an unresolved pin shows Done; clicking it calls onReviewPinResolve(id, true)', () => {
    const onReviewPinResolve = vi.fn();
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('l1'))}
        onChange={vi.fn()}
        reviewPins={[PIN]}
        onReviewPinResolve={onReviewPinResolve}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Change request 1' }));
    const popover = screen.getByRole('note');
    const done = within(popover).getByRole('button', { name: /Done/ });

    fireEvent.click(done);

    expect(onReviewPinResolve).toHaveBeenCalledWith('comment-1', true);
  });

  it('AC-S9-1: a resolved pin shows Reopen; clicking it calls onReviewPinResolve(id, false)', () => {
    const onReviewPinResolve = vi.fn();
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('l1'))}
        onChange={vi.fn()}
        reviewPins={[{ ...PIN, resolved: true, caption: 'Round 1 / Done' }]}
        onReviewPinResolve={onReviewPinResolve}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Change request 1' }));
    const popover = screen.getByRole('note');
    expect(within(popover).queryByRole('button', { name: /^Done$/ })).toBeNull();
    const reopen = within(popover).getByRole('button', { name: /Reopen/ });

    fireEvent.click(reopen);

    expect(onReviewPinResolve).toHaveBeenCalledWith('comment-1', false);
  });
});
