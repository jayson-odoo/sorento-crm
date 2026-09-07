/**
 * Rotation snap, live angle pill, Shift keep-ratio (S9, PLAN D9, AC-S9-1/2/3).
 *
 * The Transformer has no `rotationSnaps` at all before this round, and
 * `keepRatio` is hard-coded `false` - a corner drag never kept the aspect
 * ratio and a rotate never snapped to a clean angle. This is the WIRING:
 * `useShiftKey()` tracks the live key state (a rotate/resize drag runs its
 * own mousemove loop, so a snapshot taken at drag start would miss Shift
 * being pressed or released mid-drag), and `handleTransform` draws a live
 * angle label only while the ACTIVE anchor is the rotater.
 *
 * Konva does not run in jsdom; the Transformer stand-in exposes just enough
 * of its imperative API (`nodes()`, `getActiveAnchor()`, `findOne('.rotater')`,
 * `rotation()`) for `handleTransform`/`handleTransformEnd` to run against it
 * unmodified - the same idiom `TagCanvasEditor.reflow.test.tsx` uses for the
 * identical reason.
 */

import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultShapeProps } from '@/lib/dealer-kit/tag-template-types';

const hoisted = vi.hoisted(() => ({
  rotationSnaps: undefined as number[] | undefined,
  keepRatio: undefined as boolean | undefined,
  onTransform: undefined as (() => void) | undefined,
  onTransformEnd: undefined as (() => void) | undefined,
  activeAnchor: undefined as string | undefined,
  transformerRotation: 0,
}));

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
    Label: passthrough('label'),
    Tag: passthrough('tag'),
    Image: passthrough('image'),
    Text: function TextStandIn(props: { text?: string }) {
      return <div data-konva="text">{props.text}</div>;
    },
    Transformer: function TransformerStandIn(props: {
      rotationSnaps?: number[];
      keepRatio?: boolean;
      onTransform?: () => void;
      onTransformEnd?: () => void;
      ref?: React.Ref<unknown>;
    }) {
      hoisted.rotationSnaps = props.rotationSnaps;
      hoisted.keepRatio = props.keepRatio;
      hoisted.onTransform = props.onTransform;
      hoisted.onTransformEnd = props.onTransformEnd;

      const rotaterNode = { getAbsolutePosition: () => ({ x: 100, y: 50 }) };
      let nodes: unknown[] = [];
      const instance = {
        nodes: (arg?: unknown[]) => (arg === undefined ? nodes : (nodes = arg)),
        getLayer: () => ({ batchDraw: () => {} }),
        getActiveAnchor: () => hoisted.activeAnchor,
        findOne: (selector: string) => (selector === '.rotater' ? rotaterNode : undefined),
        rotation: () => hoisted.transformerRotation,
      };
      if (typeof props.ref === 'function') props.ref(instance);
      else if (props.ref && 'current' in (props.ref as { current: unknown })) {
        (props.ref as { current: unknown }).current = instance;
      }
      return (
        <div
          data-konva="transformer"
          data-rotation-snaps={JSON.stringify(props.rotationSnaps ?? [])}
          data-keep-ratio={String(Boolean(props.keepRatio))}
        />
      );
    },
  };
});

vi.mock('./KonvaTagLayer', () => ({
  KonvaTagLayer: ({
    layer,
    onSelect,
  }: {
    layer: TagLayer;
    onSelect?: (id: string, additive: boolean) => void;
  }) => <div data-testid={`layer-${layer.id}`} onClick={() => onSelect?.(layer.id, false)} />,
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

function docWith(layer: TagLayer): TagTemplateDoc {
  return { width_mm: 60, height_mm: 40, layers: [layer] };
}

function selectLayer(id: string) {
  fireEvent.click(screen.getByTestId(`layer-${id}`));
}

const ALL_15_STEPS = Array.from({ length: 24 }, (_, i) => i * 15);

beforeEach(() => {
  hoisted.rotationSnaps = undefined;
  hoisted.keepRatio = undefined;
  hoisted.onTransform = undefined;
  hoisted.onTransformEnd = undefined;
  hoisted.activeAnchor = undefined;
  hoisted.transformerRotation = 0;
});

describe('TagCanvasEditor rotation snap - Shift gates the snap list (S9, AC-S9-1)', () => {
  it('with Shift held, the Transformer receives the full 15-degree snap list', () => {
    render(<TagCanvasEditor doc={docWith(shapeLayer('l1'))} onChange={vi.fn()} />);

    expect(hoisted.rotationSnaps).toEqual([]);

    fireEvent.keyDown(window, { key: 'Shift' });

    expect(hoisted.rotationSnaps).toEqual(ALL_15_STEPS);
  });

  it('releasing Shift empties the snap list again - free rotation mid-drag', () => {
    render(<TagCanvasEditor doc={docWith(shapeLayer('l1'))} onChange={vi.fn()} />);

    fireEvent.keyDown(window, { key: 'Shift' });
    expect(hoisted.rotationSnaps).toEqual(ALL_15_STEPS);

    fireEvent.keyUp(window, { key: 'Shift' });

    expect(hoisted.rotationSnaps).toEqual([]);
  });

  it('losing window focus resets Shift, same as releasing it', () => {
    render(<TagCanvasEditor doc={docWith(shapeLayer('l1'))} onChange={vi.fn()} />);

    fireEvent.keyDown(window, { key: 'Shift' });
    expect(hoisted.rotationSnaps).toEqual(ALL_15_STEPS);

    fireEvent.blur(window);

    expect(hoisted.rotationSnaps).toEqual([]);
  });
});

describe('TagCanvasEditor rotation - Shift keeps a corner drag\'s aspect ratio (S9, AC-S9-3)', () => {
  it('keepRatio follows Shift', () => {
    render(<TagCanvasEditor doc={docWith(shapeLayer('l1'))} onChange={vi.fn()} />);

    expect(hoisted.keepRatio).toBe(false);

    fireEvent.keyDown(window, { key: 'Shift' });
    expect(hoisted.keepRatio).toBe(true);

    fireEvent.keyUp(window, { key: 'Shift' });
    expect(hoisted.keepRatio).toBe(false);
  });
});

describe('TagCanvasEditor rotation - live angle pill (S9, AC-S9-2)', () => {
  it('shows the live angle, one decimal, while the ACTIVE anchor is the rotater', () => {
    render(<TagCanvasEditor doc={docWith(shapeLayer('l1'))} onChange={vi.fn()} />);
    selectLayer('l1');

    hoisted.activeAnchor = 'rotater';
    hoisted.transformerRotation = 12.53;
    act(() => {
      hoisted.onTransform?.();
    });

    const text = Array.from(document.querySelectorAll('[data-konva="text"]')).find((el) =>
      el.textContent?.includes('°'),
    );
    expect(text?.textContent).toBe('12.5°');
  });

  it('rounds to whole degrees once Shift is snapping', () => {
    render(<TagCanvasEditor doc={docWith(shapeLayer('l1'))} onChange={vi.fn()} />);
    selectLayer('l1');

    fireEvent.keyDown(window, { key: 'Shift' });
    hoisted.activeAnchor = 'rotater';
    hoisted.transformerRotation = 45.4;
    act(() => {
      hoisted.onTransform?.();
    });

    const text = Array.from(document.querySelectorAll('[data-konva="text"]')).find((el) =>
      el.textContent?.includes('°'),
    );
    expect(text?.textContent).toBe('45°');
  });

  it('the label disappears once the active anchor is something other than the rotater', async () => {
    render(<TagCanvasEditor doc={docWith(shapeLayer('l1'))} onChange={vi.fn()} />);
    selectLayer('l1');

    hoisted.activeAnchor = 'rotater';
    hoisted.transformerRotation = 30;
    // `handleTransform` de-dupes same-tick calls (Konva's Transformer fires
    // `transform` once per attached node, not once per gesture tick) via a
    // ref cleared on a queued microtask - an `async act` awaits that
    // microtask so the SECOND call below is not silently dropped as a
    // same-tick duplicate of the first.
    await act(async () => {
      hoisted.onTransform?.();
      await Promise.resolve();
    });
    expect(
      Array.from(document.querySelectorAll('[data-konva="text"]')).some((el) =>
        el.textContent?.includes('°'),
      ),
    ).toBe(true);

    hoisted.activeAnchor = 'bottom-right';
    await act(async () => {
      hoisted.onTransform?.();
      await Promise.resolve();
    });

    expect(
      Array.from(document.querySelectorAll('[data-konva="text"]')).some((el) =>
        el.textContent?.includes('°'),
      ),
    ).toBe(false);
  });

  it('the label disappears once the transform ends', () => {
    render(<TagCanvasEditor doc={docWith(shapeLayer('l1'))} onChange={vi.fn()} />);
    selectLayer('l1');

    hoisted.activeAnchor = 'rotater';
    hoisted.transformerRotation = 30;
    act(() => {
      hoisted.onTransform?.();
    });
    expect(
      Array.from(document.querySelectorAll('[data-konva="text"]')).some((el) =>
        el.textContent?.includes('°'),
      ),
    ).toBe(true);

    act(() => {
      hoisted.onTransformEnd?.();
    });

    expect(
      Array.from(document.querySelectorAll('[data-konva="text"]')).some((el) =>
        el.textContent?.includes('°'),
      ),
    ).toBe(false);
  });
});
