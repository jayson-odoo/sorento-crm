/**
 * Image crop mode on the canvas (S8, PLAN D8, AC-S8-1/2/3/5).
 *
 * Entered ONLY from the context menu's "Crop image" (double-click on an
 * image stays a no-op, captain call 4) - `TagCanvasEditor.context-menu.
 * test.tsx` covers that menu item's own presence; this file drives the mode
 * itself: commit (Enter) writes the layer's `cropRect`, Esc leaves it
 * untouched, and the Inspector's "Reset crop" clears it.
 *
 * `useHtmlImage` needs a real `Image` load, which jsdom never fires on its
 * own - stubbed the same way `KonvaTagLayer.image.test.tsx` does. Dragging
 * the crop window uses the SAME press/move/release stand-in idiom
 * `TagCanvasEditor.polygon.test.tsx` uses for its own handles - Konva's own
 * drag is built out of these three events either way.
 */

import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { CANVAS_PX_PER_MM } from '@/lib/dealer-kit/canvas-geometry';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', async () => {
  const React = await import('react');

  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };

  interface HandleProps {
    name?: string;
    children?: React.ReactNode;
    onDragStart?: (e: { target: { x: () => number; y: () => number } }) => void;
    onDragMove?: (e: { target: { x: () => number; y: () => number } }) => void;
    onDragEnd?: (e: { target: { x: () => number; y: () => number } }) => void;
  }

  const dragged = (event: { clientX: number; clientY: number }) => ({
    target: { x: () => event.clientX, y: () => event.clientY },
  });

  function DraggableRect(props: HandleProps) {
    return (
      <div
        data-konva="rect"
        data-name={props.name}
        onMouseDown={(e) => props.onDragStart?.(dragged(e))}
        onMouseMove={(e) => props.onDragMove?.(dragged(e))}
        onMouseUp={(e) => props.onDragEnd?.(dragged(e))}
      >
        {props.children}
      </div>
    );
  }

  // `getContent()` is the Konva Stage API `handleStageContextMenu` reaches
  // for - a freshly created div has an all-zero rect in jsdom, so a click's
  // `clientX/clientY` map onto stage pixels unchanged.
  function StageStandIn({
    children,
    ref,
  }: {
    children?: React.ReactNode;
    ref?: React.Ref<{ getContent: () => HTMLElement }>;
  }) {
    const instance = { getContent: () => document.createElement('div') };
    if (typeof ref === 'function') ref(instance);
    else if (ref && 'current' in (ref as { current: unknown })) {
      (ref as { current: unknown }).current = instance;
    }
    return <div data-konva="stage">{children}</div>;
  }

  return {
    Stage: StageStandIn,
    Layer: passthrough('layer'),
    Group: passthrough('group'),
    Rect: DraggableRect,
    Circle: passthrough('circle'),
    Line: passthrough('line'),
    Transformer: passthrough('transformer'),
    Image: passthrough('image'),
    Label: passthrough('label'),
    Tag: passthrough('tag'),
    Text: passthrough('text'),
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
  // `layerDisplay` resolves an image layer's URL through `library.assetUrls`
  // (`useKitLibrary`'s own `listAssets` call, real here - only the SERVICE
  // is mocked), which is what `cropImageUrl` reads to load the source for
  // crop mode.
  listAssets: vi.fn(async () => [
    {
      id: 'a1',
      name: 'Photo',
      kind: 'image',
      tags: [],
      url: 'https://cdn.test/photo.png',
      mime_type: 'image/png',
    },
  ]),
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

/** An `Image` that "loads" at a fixed, testable size - same stub
 *  `KonvaTagLayer.image.test.tsx` uses, for the same reason. */
class StubImage {
  static width = 300;
  static height = 150;
  width = StubImage.width;
  height = StubImage.height;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private _src = '';
  set src(value: string) {
    this._src = value;
    Promise.resolve().then(() => this.onload?.());
  }
  get src() {
    return this._src;
  }
}

beforeEach(() => {
  vi.stubGlobal('Image', StubImage);
});

// 5-25mm x, 5-15mm y -> box 60x30px at CANVAS_PX_PER_MM (3). Source
// 300x150 (ratio 2) exactly matches the box's own ratio (60/30 = 2), so
// `cropFrame` fills the box with no letterboxing - the frame's origin is
// (0, 0) in the layer's own local pixel space, which keeps the drag maths
// in this file simple.
function imageLayer(cropRect?: { x: number; y: number; width: number; height: number }): TagLayer {
  return {
    id: 'img1',
    type: 'image',
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
    props: {
      kind: 'image',
      source: { type: 'asset', assetId: 'a1' },
      fit: 'contain',
      maskShape: 'none',
      cropRect,
    },
  } as TagLayer;
}

function docWith(layer: TagLayer): TagTemplateDoc {
  return { width_mm: 80, height_mm: 60, layers: [layer] };
}

/** Renders, then flushes `useKitLibrary`'s own `listAssets()` load - the
 *  asset URL `layerDisplay` resolves the crop source's `cropImageUrl` from
 *  has to have arrived before a right-click can enter crop mode. */
async function renderReady(doc: TagTemplateDoc, props: Record<string, unknown> = {}) {
  const result = render(<TagCanvasEditor doc={doc} onChange={vi.fn()} {...props} />);
  await act(async () => {
    await Promise.resolve();
  });
  return result;
}

/** Right-click INSIDE the image layer's box, select it, open its menu. */
function rightClickImage(container: HTMLElement) {
  const stageHost = container.querySelector('[data-konva="stage"]')!.parentElement!.parentElement!;
  fireEvent.contextMenu(stageHost, { clientX: 10 * CANVAS_PX_PER_MM, clientY: 10 * CANVAS_PX_PER_MM });
}

async function enterCropMode(container: HTMLElement) {
  rightClickImage(container);
  fireEvent.click(screen.getByRole('menuitem', { name: /Crop image/ }));
  // Flush the StubImage's microtask "load" so `cropImage` (and with it the
  // crop window itself) actually renders.
  await act(async () => {
    await Promise.resolve();
  });
}

function cropHandle(container: HTMLElement, name: string) {
  const el = container.querySelector(`[data-name="${name}"]`);
  if (!el) throw new Error(`no crop handle named ${name}`);
  return el as HTMLElement;
}

describe('TagCanvasEditor crop mode - entering (S8, AC-S8-1)', () => {
  it('the context menu\'s "Crop image" opens the crop window over the selected image', async () => {
    const { container } = await renderReady(docWith(imageLayer()));

    expect(container.querySelector('[data-name="crop-window"]')).toBeNull();

    await enterCropMode(container);

    expect(container.querySelector('[data-name="crop-window"]')).toBeTruthy();
    // Every one of the 8 named handles is present.
    for (const name of [
      'top-left',
      'top-center',
      'top-right',
      'middle-left',
      'middle-right',
      'bottom-left',
      'bottom-center',
      'bottom-right',
    ]) {
      expect(container.querySelector(`[data-name="crop-handle-${name}"]`)).toBeTruthy();
    }
  });
});

describe('TagCanvasEditor crop mode - commit and cancel (S8, AC-S8-3)', () => {
  it('Enter commits the dragged window and writes the layer\'s cropRect', async () => {
    let latest: TagLayer[] = [];
    const { container } = await renderReady(
      docWith(imageLayer({ x: 0, y: 0, width: 0.5, height: 0.5 })),
      {
        onLayersChange: (layers: TagLayer[]) => {
          latest = layers;
        },
      },
    );
    await enterCropMode(container);

    // Pan the window: drag INSIDE it (not on a handle) by 0.1 of the frame
    // on both axes (6px of 60, 3px of 30).
    const window_ = cropHandle(container, 'crop-window');
    fireEvent.mouseDown(window_, { clientX: 0, clientY: 0 });
    fireEvent.mouseUp(window_, { clientX: 6, clientY: 3 });

    fireEvent.keyDown(window, { key: 'Enter' });

    const committed = latest.find((l) => l.id === 'img1')!;
    expect(committed.props.kind === 'image' ? committed.props.cropRect : null).toEqual({
      x: 0.1,
      y: 0.1,
      width: 0.5,
      height: 0.5,
    });
    // The mode itself is gone once committed.
    expect(container.querySelector('[data-name="crop-window"]')).toBeNull();
  });

  it('Esc leaves the layer\'s cropRect exactly as it was (AC-S8-3)', async () => {
    let latest: TagLayer[] = [];
    const original = { x: 0, y: 0, width: 0.5, height: 0.5 };
    const { container } = await renderReady(docWith(imageLayer(original)), {
      onLayersChange: (layers: TagLayer[]) => {
        latest = layers;
      },
    });
    await enterCropMode(container);

    const window_ = cropHandle(container, 'crop-window');
    fireEvent.mouseDown(window_, { clientX: 0, clientY: 0 });
    fireEvent.mouseUp(window_, { clientX: 6, clientY: 3 });

    fireEvent.keyDown(window, { key: 'Escape' });

    // Nothing ever committed - the layer's own props are the ones it opened
    // crop mode with, byte for byte.
    const untouched = latest.find((l) => l.id === 'img1');
    if (untouched) {
      expect(untouched.props.kind === 'image' ? untouched.props.cropRect : null).toEqual(
        original,
      );
    }
    expect(container.querySelector('[data-name="crop-window"]')).toBeNull();
  });
});

describe('TagCanvasEditor crop mode - Reset crop (S8, AC-S8-5)', () => {
  /**
   * Selects the image layer through the (real, unmocked) Layers panel
   * instead of a right-click - Reset crop is an Inspector affordance with
   * no dependency on the context menu, and the menu comes with two
   * complications neither worth fighting here: Radix marks the rest of the
   * page `aria-hidden` while it is open (which hides "Reset crop" from any
   * accessible-role query even once it is visually gone), and this editor's
   * own Escape handler treats Escape as "step out of the current group",
   * which for a top-level layer with none DESELECTS it instead of merely
   * closing the menu.
   */
  // `@dnd-kit`'s sortable wrapper doubles up the accessible "button" role
  // on the same row (an outer draggable wrapper around the row's own
  // click target, both exposing the same computed name) - `title="Image"`
  // is the row's own unambiguous DOM hook, the same text `layerDisplayName`
  // gives the accessible name.
  function selectImageLayer(container: HTMLElement) {
    fireEvent.click(container.querySelector('[title="Image"]')!);
  }

  it('shows no "Reset crop" button when the layer has no crop set', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(imageLayer())} onChange={vi.fn()} />,
    );

    selectImageLayer(container);

    expect(screen.queryByRole('button', { name: 'Reset crop' })).not.toBeInTheDocument();
  });

  it('shows "Reset crop" once a crop is set, and clicking it clears cropRect', () => {
    let latest: TagLayer[] = [];
    const { container } = render(
      <TagCanvasEditor
        doc={docWith(imageLayer({ x: 0.1, y: 0.1, width: 0.5, height: 0.5 }))}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );

    selectImageLayer(container);
    fireEvent.click(screen.getByRole('button', { name: 'Reset crop' }));

    const reset = latest.find((l) => l.id === 'img1')!;
    expect(reset.props.kind === 'image' ? reset.props.cropRect : 'missing').toBeUndefined();
  });
});
