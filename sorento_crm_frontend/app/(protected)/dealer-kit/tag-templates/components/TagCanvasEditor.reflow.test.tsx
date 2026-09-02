/**
 * Live text reflow on resize (D8, S6, AC-S6-2).
 *
 * The pure fold (`reflowedTextSize`) is pinned in `lib/dealer-kit/text-reflow.test.ts`.
 * This is the wiring: `handleTransform` reads the live Konva scale on EVERY
 * tick, folds it into the node's own width/height, and resets the scale to 1
 * so the text re-wraps at its real, unchanged font size instead of visibly
 * stretching for the whole drag - and `handleTransformEnd` commits the SAME
 * fold into the saved layer.
 *
 * Konva does not run in jsdom, and `transformerRef`/`stageRef` are Konva
 * INSTANCES the real component reaches into imperatively (`.nodes()`,
 * `.findOne()`), not props a DOM-level test can drive. React 19 lets a
 * function component accept `ref` as a plain prop, so the `Stage` and
 * `Transformer` stand-ins below expose fake Konva-node-shaped objects through
 * it, close enough to the real API (`x`/`y`/`width`/`height`/`scaleX`/
 * `scaleY`/`rotation`/`findOne`) for `handleTransform`/`handleTransformEnd`
 * to run unmodified against them.
 */

import { act, fireEvent, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CANVAS_PX_PER_MM } from '@/lib/dealer-kit/canvas-geometry';
import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultTextProps } from '@/lib/dealer-kit/tag-template-types';

// -- Fake Konva nodes, shared between the mock factory and the test body ----

const hoisted = vi.hoisted(() => {
  function makeFakeNode(
    id: string,
    initial: { x: number; y: number; width: number; height: number },
  ) {
    const state = {
      ...initial,
      scaleX: 1,
      scaleY: 1,
      rotation: 0,
      textWidth: initial.width,
      textHeight: initial.height,
    };
    const textChild = {
      width: (v?: number) => (v === undefined ? state.textWidth : (state.textWidth = v)),
      height: (v?: number) => (v === undefined ? state.textHeight : (state.textHeight = v)),
    };
    return {
      id: () => id,
      x: (v?: number) => (v === undefined ? state.x : (state.x = v)),
      y: (v?: number) => (v === undefined ? state.y : (state.y = v)),
      width: (v?: number) => (v === undefined ? state.width : (state.width = v)),
      height: (v?: number) => (v === undefined ? state.height : (state.height = v)),
      scaleX: (v?: number) => (v === undefined ? state.scaleX : (state.scaleX = v)),
      scaleY: (v?: number) => (v === undefined ? state.scaleY : (state.scaleY = v)),
      rotation: (v?: number) => (v === undefined ? state.rotation : (state.rotation = v)),
      findOne: (selector: string) => (selector === 'Text' ? textChild : undefined),
      textChild,
    };
  }

  return {
    nodesById: new Map<string, ReturnType<typeof makeFakeNode>>(),
    handlers: {} as { onTransform?: () => void; onTransformEnd?: () => void },
    makeFakeNode,
  };
});

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    Stage: ({
      children,
      ref,
    }: {
      children?: React.ReactNode;
      ref?: React.Ref<{ getPointerPosition: () => null; findOne: (s: string) => unknown }>;
    }) => {
      if (typeof ref === 'function') {
        ref({
          getPointerPosition: () => null,
          findOne: (selector: string) => hoisted.nodesById.get(selector.slice(1)),
        });
      } else if (ref) {
        ref.current = {
          getPointerPosition: () => null,
          findOne: (selector: string) => hoisted.nodesById.get(selector.slice(1)),
        };
      }
      return <div data-konva="stage">{children}</div>;
    },
    Layer: passthrough('layer'),
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Line: passthrough('line'),
    Transformer: ({
      onTransform,
      onTransformEnd,
      ref,
    }: {
      onTransform?: () => void;
      onTransformEnd?: () => void;
      ref?: React.Ref<{ nodes: (arg?: unknown[]) => unknown; getLayer: () => { batchDraw: () => void } }>;
    }) => {
      hoisted.handlers.onTransform = onTransform;
      hoisted.handlers.onTransformEnd = onTransformEnd;
      let nodes: unknown[] = [];
      const instance = {
        nodes: (arg?: unknown[]) => (arg === undefined ? nodes : (nodes = arg)),
        getLayer: () => ({ batchDraw: () => {} }),
      };
      if (typeof ref === 'function') ref(instance);
      else if (ref) ref.current = instance;
      return null;
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
  }) => {
    if (!hoisted.nodesById.has(layer.id)) {
      hoisted.nodesById.set(
        layer.id,
        hoisted.makeFakeNode(layer.id, {
          x: layer.x_mm * CANVAS_PX_PER_MM,
          y: layer.y_mm * CANVAS_PX_PER_MM,
          width: layer.width_mm * CANVAS_PX_PER_MM,
          height: layer.height_mm * CANVAS_PX_PER_MM,
        }),
      );
    }
    return (
      <div data-testid={`layer-${layer.id}`} onClick={() => onSelect?.(layer.id, false)} />
    );
  },
}));

vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => {}),
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

function textLayerDoc(): TagTemplateDoc {
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
    props: { ...defaultTextProps(), text: 'Hello', fontSize: 10 },
  };
  return { width_mm: 60, height_mm: 40, layers: [layer] };
}

beforeEach(() => {
  hoisted.nodesById.clear();
  hoisted.handlers = {};
});

describe('TagCanvasEditor live text reflow (AC-S6-2)', () => {
  it('reflows the box live on every transform tick and commits the same size on release, font size unchanged', () => {
    let currentLayers: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={textLayerDoc()}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          currentLayers = layers;
        }}
      />,
    );

    act(() => {
      fireEvent.click(document.querySelector('[data-testid="layer-text-1"]')!);
    });

    const node = hoisted.nodesById.get('text-1')!;
    // A corner handle drags both axes at once.
    node.scaleX(1.5);
    node.scaleY(1.2);

    act(() => {
      hoisted.handlers.onTransform?.();
    });

    // Live: the scale is folded into width/height and reset - Konva re-wraps
    // the text at its own unchanged fontSize instead of stretching it.
    expect(node.scaleX()).toBe(1);
    expect(node.scaleY()).toBe(1);
    expect(node.width()).toBeCloseTo(20 * CANVAS_PX_PER_MM * 1.5);
    expect(node.height()).toBeCloseTo(6 * CANVAS_PX_PER_MM * 1.2);
    // The Text child inside the Group reflows WITH it, on the same tick.
    expect(node.textChild.width()).toBeCloseTo(node.width());
    expect(node.textChild.height()).toBeCloseTo(node.height());

    act(() => {
      hoisted.handlers.onTransformEnd?.();
    });

    const saved = currentLayers.find((l) => l.id === 'text-1')!;
    expect(saved.width_mm).toBeCloseTo(20 * 1.5);
    expect(saved.height_mm).toBeCloseTo(6 * 1.2);
    expect(saved.props.kind === 'text' && saved.props.fontSize).toBe(10);
  });

  it('reflows an EDGE handle drag too - one axis scaled, the other untouched', () => {
    let currentLayers: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={textLayerDoc()}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          currentLayers = layers;
        }}
      />,
    );

    act(() => {
      fireEvent.click(document.querySelector('[data-testid="layer-text-1"]')!);
    });

    const node = hoisted.nodesById.get('text-1')!;
    node.scaleX(2);
    // scaleY left at 1 - an edge handle only drags one axis.

    act(() => {
      hoisted.handlers.onTransform?.();
    });
    act(() => {
      hoisted.handlers.onTransformEnd?.();
    });

    const saved = currentLayers.find((l) => l.id === 'text-1')!;
    expect(saved.width_mm).toBeCloseTo(20 * 2);
    expect(saved.height_mm).toBeCloseTo(6);
    expect(saved.props.kind === 'text' && saved.props.fontSize).toBe(10);
  });
});
