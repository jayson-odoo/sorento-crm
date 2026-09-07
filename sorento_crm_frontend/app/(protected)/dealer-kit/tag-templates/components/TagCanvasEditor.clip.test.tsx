/**
 * WYSIWYG after a shrink (S9 review S4): a layer dragged or resized past the
 * tag's own edge must be hidden on screen exactly the way `TagSheetRenderer`
 * clips it on the printed sheet (`overflow: hidden`), not still visible on a
 * canvas that quietly disagrees with what the PDF will show.
 *
 * Konva does not run in jsdom, so this pins the WIRING rather than a
 * rendered pixel: the layers sit inside a `Group` whose `clipFunc` draws the
 * exact same rectangle the white artboard background itself is drawn at
 * (`canvasWidthPx`/`canvasHeightPx`) - the one geometry the editor already
 * computes and the one this test can read off the background `Rect` without
 * having to reproduce the zoom/scale arithmetic itself.
 *
 * Extended (#720 fix, S4, AC-S4-1/3): a layer the resize left past the edge
 * is not just clipped away - it is drawn a SECOND time, unclipped, at 30%
 * opacity, fully interactive (`TagCanvasEditor`'s own ghost pass), and the
 * Layers panel row for it carries an "outside" marker. `KonvaTagLayer` is
 * stood in for by a clickable div (same idiom as `TagCanvasEditor.polygon.
 * test.tsx`) rather than `() => null`, so the ghost pass actually renders
 * something this file can assert against; `LayersPanel` itself is left
 * UNMOCKED, since the marker is its own real behaviour, not this file's.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultTextProps } from '@/lib/dealer-kit/tag-template-types';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

const capturedRects: { name?: string; x?: number; y?: number; width?: number; height?: number }[] =
  [];
const capturedGroups: { clipFunc?: (ctx: { rect: (...args: number[]) => void }) => void }[] = [];

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    Stage: passthrough('stage'),
    Layer: passthrough('layer'),
    Group: (props: {
      children?: React.ReactNode;
      clipFunc?: (ctx: { rect: (...args: number[]) => void }) => void;
    }) => {
      capturedGroups.push({ clipFunc: props.clipFunc });
      return <div data-konva="group">{props.children}</div>;
    },
    Rect: (props: {
      name?: string;
      x?: number;
      y?: number;
      width?: number;
      height?: number;
      children?: React.ReactNode;
    }) => {
      capturedRects.push(props);
      return <div data-konva="rect" data-name={props.name} />;
    },
    Line: passthrough('line'),
    Transformer: passthrough('transformer'),
  };
});

vi.mock('./KonvaTagLayer', () => ({
  KonvaTagLayer: ({
    layer,
    onSelect,
    interactionId,
    opacity,
  }: {
    layer: TagLayer;
    onSelect?: (id: string, additive: boolean) => void;
    interactionId?: string;
    opacity?: number;
  }) => (
    <div
      data-testid={`layer-${layer.id}`}
      data-opacity={opacity ?? 1}
      onClick={() => onSelect?.(interactionId ?? layer.id, false)}
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

function doc(): TagTemplateDoc {
  const layer: TagLayer = {
    id: 'text-1',
    type: 'text',
    x_mm: 5,
    y_mm: 5,
    width_mm: 20,
    height_mm: 6,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultTextProps(), text: 'Hello' },
  };
  return { width_mm: 60, height_mm: 40, layers: [layer] };
}

describe('TagCanvasEditor artboard clip (S9 review S4)', () => {
  it('clips the layers Group to exactly the artboard background rect', () => {
    capturedRects.length = 0;
    capturedGroups.length = 0;

    render(<TagCanvasEditor doc={doc()} onChange={vi.fn()} />);

    const artboardBg = capturedRects.filter((r) => r.name === 'artboard-bg').at(-1);
    expect(artboardBg).toBeDefined();
    expect(artboardBg!.width).toBeGreaterThan(0);
    expect(artboardBg!.height).toBeGreaterThan(0);

    // The layers Group's clipFunc draws the SAME rectangle the background is
    // drawn at - the artboard's own bounds, not some other guess at the
    // tag's size. (Re-renders after mount - e.g. the fit-to-view effect
    // measuring its container - can call the mocked component more than
    // once; the LAST render is what actually stayed on screen.)
    expect(capturedGroups.length).toBeGreaterThan(0);
    const clipFunc = capturedGroups[capturedGroups.length - 1].clipFunc;
    expect(clipFunc).toBeTypeOf('function');

    const rectCalls: number[][] = [];
    const ctx = { rect: (...args: number[]) => rectCalls.push(args) };
    clipFunc!(ctx);

    expect(rectCalls).toEqual([[0, 0, artboardBg!.width, artboardBg!.height]]);
  });
});

// ---------------------------------------------------------------------------
// Ghost pass (#720 fix, S4, AC-S4-1/3): a layer a resize left past the edge
// stays visible (dimmed) and interactive OUTSIDE the clip, and the Layers
// panel flags it - it never actually disappears, only the clipped copy does.
// ---------------------------------------------------------------------------

function overflowingLayerDoc(): TagTemplateDoc {
  const layer: TagLayer = {
    id: 'text-1',
    type: 'text',
    // 55 + 20 = 75mm, well past the 60mm-wide artboard below.
    x_mm: 55,
    y_mm: 5,
    width_mm: 20,
    height_mm: 6,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultTextProps(), text: 'Hello' },
  };
  return { width_mm: 60, height_mm: 40, layers: [layer] };
}

describe('TagCanvasEditor ghost pass for off-artboard layers (S4, AC-S4-1/3)', () => {
  it('draws the overflowing layer twice: the clipped copy AND a selectable ghost at 30% opacity', () => {
    render(<TagCanvasEditor doc={overflowingLayerDoc()} onChange={vi.fn()} />);

    // The clipped copy, same as any layer - it still exists and still draws,
    // even though the artboard Group's own clipFunc hides the part past the
    // edge in a real Konva render.
    expect(screen.getByTestId('layer-text-1')).toBeInTheDocument();

    // The ghost pass: a SECOND node for the same layer, drawn outside the
    // clip at reduced opacity (AC-S4-1). Its own Konva id is suffixed so it
    // never collides with the clipped copy above.
    const ghost = screen.getByTestId('layer-text-1-ghost');
    expect(ghost.getAttribute('data-opacity')).toBe('0.3');
  });

  it('the ghost is fully interactive - clicking it selects the REAL layer (AC-S4-1)', () => {
    render(<TagCanvasEditor doc={overflowingLayerDoc()} onChange={vi.fn()} />);

    // Nothing selected yet: Delete is disabled.
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled();

    fireEvent.click(screen.getByTestId('layer-text-1-ghost'));

    // `interactionId` on the ghost routes the click to the layer's REAL id
    // (`text-1`, not `text-1-ghost`) - selection now holds, so Delete arms.
    expect(screen.getByRole('button', { name: 'Delete' })).not.toBeDisabled();
  });

  it('flags the overflowing layer in the Layers panel with the outside marker', () => {
    render(<TagCanvasEditor doc={overflowingLayerDoc()} onChange={vi.fn()} />);

    expect(
      screen.getByTitle('Partly outside the tag, it will not print'),
    ).toBeInTheDocument();
  });

  it('the outside marker stays inside the Layers panel row, not clipped past it (AC-S4-3 review, #720)', () => {
    render(<TagCanvasEditor doc={overflowingLayerDoc()} onChange={vi.fn()} />);

    const marker = screen.getByTitle('Partly outside the tag, it will not print');
    // `shrink-0`, same as the eye/lock buttons after it - none of the row's
    // fixed-width content shrinks; only the layer name does.
    expect(marker.className).toContain('shrink-0');

    // A sibling of the truncating NAME (not nested inside it, not nested
    // inside anything else) - both direct children of the SAME flex row, so
    // there is one flex context deciding what shrinks and what does not.
    const row = marker.parentElement!;
    const name = Array.from(row.children).find((el) =>
      el.className.includes('truncate'),
    ) as HTMLElement;
    expect(name).toBeTruthy();
    expect(name.className).toContain('min-w-0');
    expect(name.className).toContain('flex-1');
    expect(row.className).toContain('flex');

    // Radix `ScrollArea` wraps its own children in an inline
    // `display: table` div sized to CONTENT (min-width: 100% only, no
    // max-width) - a row's `flex-1 min-w-0 truncate` name never actually
    // gets squeezed there, so the panel's own overflow-x just clips
    // whatever ends up rightmost instead of letting the name shrink first.
    // The panel is a plain overflow container now, not that primitive.
    expect(document.querySelector('[data-radix-scroll-area-viewport]')).toBeNull();
  });

  it('a fully-inside layer draws once - no ghost, no marker (AC-S4-5)', () => {
    render(<TagCanvasEditor doc={doc()} onChange={vi.fn()} />);

    expect(screen.getByTestId('layer-text-1')).toBeInTheDocument();
    expect(screen.queryByTestId('layer-text-1-ghost')).not.toBeInTheDocument();
    expect(
      screen.queryByTitle('Partly outside the tag, it will not print'),
    ).not.toBeInTheDocument();
  });
});
