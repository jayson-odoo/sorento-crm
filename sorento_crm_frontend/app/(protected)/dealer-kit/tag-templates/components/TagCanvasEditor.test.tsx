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

import type {
  TagBindingData,
  TagLayer,
  TagTemplateDoc,
} from '@/lib/dealer-kit/tag-template-types';
import { defaultShapeProps, defaultTextProps } from '@/lib/dealer-kit/tag-template-types';
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
  KonvaTagLayer: ({
    layer,
    onSelect,
  }: {
    layer: TagLayer;
    onSelect?: (id: string, additive: boolean) => void;
  }) => (
    <div
      data-testid={`layer-${layer.id}`}
      onClick={() => onSelect?.(layer.id, false)}
    />
  ),
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

// ---------------------------------------------------------------------------
// S16 (code review, D21): the inspector's "Copy rendered text" preview is
// wired off `selectedResolvedText`, which used to be `resolveSlotText` alone
// - null for any layer with NO `slot_binding`, so an unbound text layer whose
// OWN content carries a token (`Made of {{spec.material}}`, D57) never showed
// a preview even though `isDynamic` correctly flagged it as one. Fixed to
// `layerText` (the same function the print renderer resolves a layer's final
// text through), which this pins through the real component, not a hand-fed
// `resolvedText` prop (that half is `InspectorPanel.test.tsx` AC-S16-1/S16-2).
// ---------------------------------------------------------------------------

function textLayer(id: string, text: string): TagLayer {
  return {
    id,
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 20,
    height_mm: 6,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultTextProps(), text },
  };
}

const LINE_BOUND_DATA: TagBindingData = {
  kind: 'line',
  line: {
    tag_id: 'tag-1',
    line_id: 'line-1',
    tag_label: '1a',
    open_groups: [],
    parts: [],
    code: 'SRTWT8267-GM',
    name: 'Kitchen Sink',
    dimensions: '800 x 500 x 220 mm',
    spec_lines: '',
    specs: [{ key: 'dim_length', label: 'Length', value: '800', unit: 'mm' }],
    set_members: '',
    images: [],
    list_price: 1599,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    barcode: null,
  },
};

describe('TagCanvasEditor inspector preview - unbound text with a token (S16)', () => {
  it('an unbound text layer "L{{spec.dim_length}}mm" previews "L800mm" with a Copy button', async () => {
    const doc: TagTemplateDoc = {
      width_mm: 60,
      height_mm: 40,
      layers: [textLayer('dims', 'L{{spec.dim_length}}mm')],
    };
    render(
      <TagCanvasEditor doc={doc} onChange={vi.fn()} boundData={LINE_BOUND_DATA} />,
    );

    fireEvent.click(screen.getByTestId('layer-dims'));

    expect(await screen.findByText('L800mm')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Copy rendered text' }),
    ).toBeInTheDocument();
  });
});
