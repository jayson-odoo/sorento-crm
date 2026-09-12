/**
 * Right-click on an image layer opens the LAYER menu (S10, PLAN D10,
 * observed bug, AC-S10-1/2).
 *
 * Screenshot on prod: right-click on a selected image layer showed the
 * EMPTY-canvas menu (Paste, Select All, Fit to View, Zoom 100%) instead of
 * the layer one (Cut, Copy, Paste, Duplicate, Crop image...). The fix lives
 * in `handleStageContextMenu`: a plain REACT `onContextMenu` on the canvas's
 * own wrapping div (not a Konva event), which converts the click's
 * `clientX/clientY` through `stageRef.current.getContent().
 * getBoundingClientRect()` into mm and hit-tests `layers` directly with
 * `hitLayerAt` - independent of Konva's own event target, which is what a
 * plain image node's hit region used to confuse (AC-S10-3: the candidates
 * `PLAN-price-tag-r6.md` S10 named - `pointerMm()` returning null off the
 * Konva event target, `hitLayerAt` skipping a non-entered group, a z-order
 * tie with the badge - the fix moved off the Konva event path entirely
 * rather than picking one of them).
 *
 * `KonvaTagLayer` renders nothing here - the menu's own choice is decided
 * entirely from `layers` + the click's mm position, never from what Konva
 * actually rendered, so a `() => null` stand-in is enough (same idiom
 * `TagCanvasEditor.clip.test.tsx` used before it needed a fuller one for a
 * different reason).
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultShapeProps } from '@/lib/dealer-kit/tag-template-types';
import { CANVAS_PX_PER_MM } from '@/lib/dealer-kit/canvas-geometry';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    // `getContent()` is the one Konva Stage API `handleStageContextMenu`
    // reaches for - the DOM node it calls `getBoundingClientRect()` on. A
    // freshly created div has an all-zero rect in jsdom (no real layout
    // engine), so a click's `clientX/clientY` map onto stage pixels
    // UNCHANGED - the coordinates below are chosen with exactly that in mind.
    Stage: ({
      children,
      ref,
    }: {
      children?: React.ReactNode;
      ref?: React.Ref<{ getContent: () => HTMLElement }>;
    }) => {
      const instance = { getContent: () => document.createElement('div') };
      if (typeof ref === 'function') ref(instance);
      else if (ref && 'current' in (ref as { current: unknown })) {
        (ref as { current: unknown }).current = instance;
      }
      return <div data-konva="stage">{children}</div>;
    },
    Layer: passthrough('layer'),
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Circle: passthrough('circle'),
    Line: passthrough('line'),
    Transformer: passthrough('transformer'),
  };
});

vi.mock('./KonvaTagLayer', () => ({
  KonvaTagLayer: () => null,
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

function imageLayer(id: string): TagLayer {
  return {
    id,
    type: 'image',
    // 5-25mm x, 5-15mm y -> 15-75px x, 15-45px y at CANVAS_PX_PER_MM (3).
    x_mm: 5,
    y_mm: 5,
    width_mm: 20,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { kind: 'image', source: null, fit: 'contain', maskShape: 'none' },
  } as TagLayer;
}

function shapeLayer(id: string): TagLayer {
  return {
    id,
    type: 'shape',
    x_mm: 5,
    y_mm: 5,
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

function docWith(...layers: TagLayer[]): TagTemplateDoc {
  return { width_mm: 80, height_mm: 60, layers };
}

/** A point INSIDE the image layer's box, in stage pixels. */
const INSIDE_IMAGE = { clientX: 10 * CANVAS_PX_PER_MM, clientY: 10 * CANVAS_PX_PER_MM };
/** Well past the 80x60mm artboard - guaranteed empty canvas. */
const EMPTY_CANVAS = { clientX: 500, clientY: 500 };

function rightClickCanvas(container: HTMLElement, point: { clientX: number; clientY: number }) {
  const stageHost = container.querySelector('[data-konva="stage"]')!.parentElement!.parentElement!;
  fireEvent.contextMenu(stageHost, point);
}

describe('TagCanvasEditor context menu (S10, AC-S10-1)', () => {
  it('right-click on an image layer opens the LAYER menu - Cut, Copy, Duplicate, Crop image', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(imageLayer('img1'))} onChange={vi.fn()} />,
    );

    rightClickCanvas(container, INSIDE_IMAGE);

    expect(screen.getByRole('menuitem', { name: /Cut/ })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /Copy/ })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /Duplicate/ })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /Crop image/ })).toBeInTheDocument();
    // The empty-canvas menu's own items are absent.
    expect(screen.queryByRole('menuitem', { name: /Select All/ })).not.toBeInTheDocument();
  });

  it('right-clicking the image SELECTS it - the layer menu is not shown for a stale selection', () => {
    const { container } = render(
      <TagCanvasEditor
        doc={docWith(imageLayer('img1'), shapeLayer('other'))}
        onChange={vi.fn()}
      />,
    );

    // Nothing selected yet - a right-click still resolves the menu off the
    // CLICKED layer, not whatever was selected before (there was nothing).
    rightClickCanvas(container, INSIDE_IMAGE);

    expect(screen.getByRole('menuitem', { name: /Crop image/ })).toBeInTheDocument();
  });

  it('right-click on empty canvas still opens Paste / Select All / Fit to View / Zoom 100% (AC-S10-2)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(imageLayer('img1'))} onChange={vi.fn()} />,
    );

    rightClickCanvas(container, EMPTY_CANVAS);

    expect(screen.getByRole('menuitem', { name: /Paste/ })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /Select All/ })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /Fit to View/ })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /Zoom 100%/ })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /Crop image/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /^Cut/ })).not.toBeInTheDocument();
  });

  it('a non-image layer never offers Crop image', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1'))} onChange={vi.fn()} />,
    );

    rightClickCanvas(container, INSIDE_IMAGE);

    expect(screen.getByRole('menuitem', { name: /Cut/ })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /Crop image/ })).not.toBeInTheDocument();
  });
});
