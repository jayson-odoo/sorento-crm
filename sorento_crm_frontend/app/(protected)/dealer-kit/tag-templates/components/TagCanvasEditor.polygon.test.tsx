/**
 * Polygon select mode vs edit-points mode (S5, PLAN D5).
 *
 * r5 gave a selected polygon (or a boxed list-only price badge) vertex/edge
 * handles the instant it was clicked, at the cost of every Transformer
 * resize anchor (AC-S4-10 from that round) - a polygon could not be resized
 * by dragging its box at all. S5 splits that one state into two, the
 * Figma/Illustrator pattern: a single click SELECTS (full anchor set, no
 * vertex handles, a box-drag resizes the shape via its normalised points);
 * double-click, Enter, or the Inspector's "Edit points" button drops into
 * EDIT-POINTS mode (anchors gone, vertex/edge handles back) - everything the
 * geometry tests below exercised in r5 now runs inside that mode instead.
 *
 * The geometry itself (`movePoint`/`moveEdge`/`refitPolygon`/`snapDelta`) is
 * pinned in `lib/dealer-kit/polygon-path.test.ts`. This is the WIRING.
 *
 * Konva does not run in jsdom, so `react-konva` is stood in for by divs that
 * carry the props a handle is identified and driven by - the same pattern
 * `TagCanvasEditor.guides.test.tsx` uses for a ruler guide's `stroke`, and
 * `TagCanvasEditor.reflow.test.tsx` uses for a fake Konva node the
 * Transformer's own imperative API (`.nodes()`, `x()/y()/scaleX()/scaleY()`)
 * can run against unmodified.
 */

import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { polygonPoints } from '@/lib/dealer-kit/polygon-path';
import { CANVAS_PX_PER_MM } from '@/lib/dealer-kit/canvas-geometry';

// -- Stand-ins ---------------------------------------------------------------

/** What the stand-in records for the test, hoisted with the mock factory. */
const konva = vi.hoisted(() => ({
  positions: [] as { x: number; y: number }[],
  anchors: [] as unknown[],
  rotateEnabled: [] as unknown[],
  nodesById: new Map<
    string,
    {
      id: () => string;
      x: (v?: number) => number;
      y: (v?: number) => number;
      width: (v?: number) => number;
      height: (v?: number) => number;
      scaleX: (v?: number) => number;
      scaleY: (v?: number) => number;
      rotation: (v?: number) => number;
      findOne: () => undefined;
    }
  >(),
  onTransformEnd: undefined as (() => void) | undefined,
  transformerNodes: [] as unknown[],
}));

function fakeNode(layer: TagLayer) {
  const state = {
    x: layer.x_mm * CANVAS_PX_PER_MM,
    y: layer.y_mm * CANVAS_PX_PER_MM,
    width: layer.width_mm * CANVAS_PX_PER_MM,
    height: layer.height_mm * CANVAS_PX_PER_MM,
    scaleX: 1,
    scaleY: 1,
    rotation: layer.rotation_deg,
  };
  return {
    id: () => layer.id,
    x: (v?: number) => (v === undefined ? state.x : (state.x = v)),
    y: (v?: number) => (v === undefined ? state.y : (state.y = v)),
    width: (v?: number) => (v === undefined ? state.width : (state.width = v)),
    height: (v?: number) => (v === undefined ? state.height : (state.height = v)),
    scaleX: (v?: number) => (v === undefined ? state.scaleX : (state.scaleX = v)),
    scaleY: (v?: number) => (v === undefined ? state.scaleY : (state.scaleY = v)),
    rotation: (v?: number) => (v === undefined ? state.rotation : (state.rotation = v)),
    findOne: () => undefined,
  };
}

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', async () => {
  const React = await import('react');

  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };

  interface HandleProps {
    name?: string;
    x?: number;
    y?: number;
    children?: React.ReactNode;
    onDragStart?: (e: { target: { x: () => number; y: () => number } }) => void;
    onDragMove?: (e: {
      target: { x: () => number; y: () => number };
      evt: { shiftKey: boolean };
    }) => void;
    onDragEnd?: (e: {
      target: {
        x: () => number;
        y: () => number;
        position: (p: { x: number; y: number }) => void;
      };
      evt: { shiftKey: boolean };
    }) => void;
  }

  // A Konva drag hands the handler the NODE; everything this component reads
  // off it is its position, so the stand-in answers the pointer's own client
  // coordinates. Press / move / release stands in for the drag itself: jsdom
  // has no DragEvent that carries coordinates, and Konva's drag is built out
  // of these three anyway. `evt.shiftKey` carries the fireEvent option
  // through, the same one Konva's own `evt` would carry (r5 S1).
  const dragged = (event: { clientX: number; clientY: number; shiftKey?: boolean }) => ({
    target: {
      x: () => event.clientX,
      y: () => event.clientY,
      position: (p: { x: number; y: number }) => konva.positions.push(p),
    },
    evt: { shiftKey: event.shiftKey ?? false },
  });

  const draggable = (kind: string) =>
    function KonvaDraggableStandIn(props: HandleProps) {
      // Konva delivers a `dragend` even when the node is DESTROYED mid-drag:
      // the drag manager holds the node, not the scene graph, so unmounting a
      // handle while the button is still down fires the handler one last time
      // at the position the pointer had reached - the stand-in has to do it
      // too, held in a ref and fired from the unmount cleanup.
      const live = React.useRef<{ clientX: number; clientY: number; shiftKey: boolean } | null>(
        null,
      );
      const latest = React.useRef(props);
      latest.current = props;

      React.useEffect(
        () => () => {
          if (live.current) latest.current.onDragEnd?.(dragged(live.current));
        },
        [],
      );

      return (
        <div
          data-konva={kind}
          data-name={props.name}
          data-x={props.x}
          data-y={props.y}
          onMouseDown={(e) => {
            live.current = { clientX: e.clientX, clientY: e.clientY, shiftKey: e.shiftKey };
            props.onDragStart?.(dragged(e));
          }}
          onMouseMove={(e) => {
            if (live.current) {
              live.current = { clientX: e.clientX, clientY: e.clientY, shiftKey: e.shiftKey };
            }
            props.onDragMove?.(dragged(e));
          }}
          onMouseUp={(e) => {
            live.current = null;
            props.onDragEnd?.(dragged(e));
          }}
        >
          {props.children}
        </div>
      );
    };

  // Stage forwards a `findOne(#id)` that answers from `konva.nodesById` - the
  // same map `KonvaTagLayer` below registers a layer's fake Konva node into.
  // `TagCanvasEditor`'s own attach-effect calls exactly this (`stage.findOne`)
  // to hand the Transformer its selected nodes, so wiring it here is what
  // makes a REAL resize (scale on the node, then `onTransformEnd`) reach the
  // component's own commit path unmodified - the same idiom
  // `TagCanvasEditor.reflow.test.tsx` uses for the identical reason.
  function StageStandIn(props: {
    children?: React.ReactNode;
    ref?: React.Ref<{ getPointerPosition: () => null; findOne: (s: string) => unknown }>;
  }) {
    const instance = {
      getPointerPosition: () => null,
      findOne: (selector: string) => konva.nodesById.get(selector.slice(1)),
    };
    if (typeof props.ref === 'function') props.ref(instance);
    else if (props.ref && 'current' in (props.ref as { current: unknown })) {
      (props.ref as { current: unknown }).current = instance;
    }
    return <div data-konva="stage">{props.children}</div>;
  }

  return {
    Stage: StageStandIn,
    Layer: passthrough('layer'),
    Group: draggable('group'),
    Rect: draggable('rect'),
    Circle: draggable('circle'),
    Line: passthrough('line'),
    Transformer: function TransformerStandIn(props: {
      enabledAnchors?: unknown[];
      rotateEnabled?: boolean;
      ref?: React.Ref<unknown>;
      onTransformEnd?: () => void;
    }) {
      konva.anchors.push(props.enabledAnchors);
      konva.rotateEnabled.push(props.rotateEnabled);
      konva.onTransformEnd = props.onTransformEnd;
      // `konva.transformerNodes` lives on the module-level hoisted object,
      // not a closure local: `TransformerStandIn` is a plain function
      // component, so every parent re-render (selecting a layer among them)
      // would otherwise hand out a FRESH instance with `nodes` reset to
      // empty, throwing away whatever the attach-effect had just set on the
      // previous render's instance.
      const instance = {
        nodes: (arg?: unknown[]) =>
          arg === undefined ? konva.transformerNodes : (konva.transformerNodes = arg),
        getLayer: () => ({ batchDraw: () => {} }),
        getActiveAnchor: () => undefined,
      };
      if (typeof props.ref === 'function') props.ref(instance);
      else if (props.ref && 'current' in (props.ref as { current: unknown })) {
        (props.ref as { current: unknown }).current = instance;
      }
      return (
        <div
          data-konva="transformer"
          data-anchors={JSON.stringify(props.enabledAnchors)}
          data-rotate-enabled={String(props.rotateEnabled)}
        />
      );
    },
  };
});

vi.mock('./KonvaTagLayer', () => ({
  KonvaTagLayer: ({
    layer,
    onSelect,
    onDoubleClick,
  }: {
    layer: TagLayer;
    onSelect?: (id: string, additive: boolean) => void;
    onDoubleClick?: (id: string) => void;
  }) => {
    if (!konva.nodesById.has(layer.id)) konva.nodesById.set(layer.id, fakeNode(layer));
    return (
      <div
        data-testid={`layer-${layer.id}`}
        data-x={layer.x_mm}
        data-y={layer.y_mm}
        data-w={layer.width_mm}
        data-h={layer.height_mm}
        data-points={
          layer.props.kind === 'shape' && layer.props.shape === 'polygon'
            ? JSON.stringify(polygonPoints(layer.props))
            : undefined
        }
        onClick={() => onSelect?.(layer.id, false)}
        onDoubleClick={() => onDoubleClick?.(layer.id)}
      />
    );
  },
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

// -- The document under test --------------------------------------------------

/**
 * 40mm x 20mm at the origin. The stage is never measured in jsdom, so the
 * view stays at zoom 1 and `CANVAS_PX_PER_MM` (3) is the whole scale: the
 * layer box is 120 x 60 px and every handle position below is exact.
 */
const W_PX = 120;
const H_PX = 60;

const FULL_ANCHORS = [
  'top-left',
  'top-right',
  'bottom-left',
  'bottom-right',
  'middle-left',
  'middle-right',
  'top-center',
  'bottom-center',
];

function shapeLayer(
  id: string,
  shape: 'polygon' | 'rect',
  extra: Record<string, unknown> = {},
  overrides: Partial<TagLayer> = {},
): TagLayer {
  return {
    id,
    type: 'shape',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 20,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'shape',
      shape,
      fill: '#e0e0e0',
      stroke: '#999999',
      strokeWidth: 0.5,
      cornerRadius: 0,
      ...extra,
    },
    ...overrides,
  } as TagLayer;
}

function boxedBadge(id: string): TagLayer {
  return {
    id,
    type: 'price_badge',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 20,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'price_badge',
      variant: 'list_only',
      fill: '#ffffff',
      textColor: '#000000',
      cornerRadius: 0,
      showNett: true,
      showBox: true,
    },
  } as unknown as TagLayer;
}

function docWith(...layers: TagLayer[]): TagTemplateDoc {
  return { width_mm: 60, height_mm: 40, layers };
}

function handle(container: HTMLElement, name: string) {
  const element = container.querySelector(`[data-name="${name}"]`);
  if (!element) throw new Error(`no handle named ${name}`);
  return element as HTMLElement;
}

function queryHandle(container: HTMLElement, name: string) {
  return container.querySelector(`[data-name="${name}"]`);
}

function pointsOf(layerId = 'sh1') {
  return JSON.parse(screen.getByTestId(`layer-${layerId}`).getAttribute('data-points') ?? 'null');
}

function boxOf(layerId = 'sh1') {
  const node = screen.getByTestId(`layer-${layerId}`);
  return {
    x: Number(node.getAttribute('data-x')),
    y: Number(node.getAttribute('data-y')),
    width: Number(node.getAttribute('data-w')),
    height: Number(node.getAttribute('data-h')),
  };
}

/** Single click: SELECT mode (AC-S5-1). */
function selectShape(id = 'sh1') {
  fireEvent.click(screen.getByTestId(`layer-${id}`));
}

/** Double click: EDIT-POINTS mode (AC-S5-2). Konva fires a plain click first,
 * same as a real pointer would - the component's own click handler runs
 * before the double-click one either way. */
function enterEditPoints(id = 'sh1') {
  fireEvent.click(screen.getByTestId(`layer-${id}`));
  fireEvent.doubleClick(screen.getByTestId(`layer-${id}`));
}

function lastAnchors() {
  return konva.anchors.at(-1);
}

function lastRotateEnabled() {
  return konva.rotateEnabled.at(-1);
}

beforeEach(() => {
  vi.clearAllMocks();
  konva.positions.length = 0;
  konva.anchors.length = 0;
  konva.rotateEnabled.length = 0;
  konva.nodesById.clear();
  konva.transformerNodes = [];
  konva.onTransformEnd = undefined;
});

// ---------------------------------------------------------------------------
// Select mode (AC-S5-1, AC-S5-4)
// ---------------------------------------------------------------------------

describe('select mode - single click (S5, AC-S5-1)', () => {
  it('shows the full Transformer anchor set and no vertex/edge handles', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );

    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();

    selectShape();

    expect(lastAnchors()).toEqual(FULL_ANCHORS);
    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();
    expect(queryHandle(container, 'polygon-edge-0')).toBeNull();
  });

  it('keeps the rotate handle in select mode (S5 review)', () => {
    render(<TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />);

    selectShape();

    expect(lastRotateEnabled()).toBe(true);
  });

  it('gives a boxed list-only price badge the same select mode (AC-S5-4)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(boxedBadge('sh1'))} onChange={vi.fn()} />,
    );

    selectShape();

    expect(lastAnchors()).toEqual(FULL_ANCHORS);
    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();
  });

  it('leaves a rectangle on its ordinary anchors regardless - it has no points to edit', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'rect'))} onChange={vi.fn()} />,
    );

    selectShape();

    expect(lastAnchors()).toEqual(FULL_ANCHORS);
    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();
  });

  it('a box-drag resize in select mode grows the box and leaves the normalised points untouched (AC-S5-1)', () => {
    let latestLayers: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('sh1', 'polygon'))}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          latestLayers = layers;
        }}
      />,
    );

    // The attach-effect only wires the Transformer to a SELECTED node, so
    // the resize below has to follow a real select first.
    selectShape();
    expect(lastAnchors()).toEqual(FULL_ANCHORS);

    const freshShapeProps = shapeLayer('sh1', 'polygon').props;
    const before =
      freshShapeProps.kind === 'shape' ? polygonPoints(freshShapeProps) : [];

    // A corner-anchor drag: Konva reports it as a `scale` on the node the
    // Transformer is attached to, not a new width/height directly.
    const node = konva.nodesById.get('sh1')!;
    node.scaleX(1.5);
    node.scaleY(2);
    act(() => {
      konva.onTransformEnd?.();
    });

    const resized = latestLayers.find((l) => l.id === 'sh1')!;
    // Box grew by exactly the scale (40mm * 1.5, 20mm * 2) - the resize
    // reached the layer.
    expect(resized.width_mm).toBeCloseTo(60);
    expect(resized.height_mm).toBeCloseTo(40);
    // The shape's own points are normalised 0-1 against that box, so a plain
    // box resize needs no change to them at all - this is the whole point of
    // select mode not touching `props`.
    // Comparing the RESOLVED points (as `KonvaTagLayer`/the Layers panel see
    // them, defaulting when absent) rather than the raw `props.points`: a
    // fresh shape carries no explicit points until something writes them,
    // and select-mode's whole point is that a box resize is not that
    // something.
    expect(resized.props.kind === 'shape' ? polygonPoints(resized.props) : null).toEqual(before);
  });
});

// ---------------------------------------------------------------------------
// Entering edit-points mode (AC-S5-2)
// ---------------------------------------------------------------------------

describe('entering edit-points mode (S5, AC-S5-2)', () => {
  it('double-click shows vertex + edge handles and clears the Transformer anchors', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );

    enterEditPoints();

    for (let i = 0; i < 4; i += 1) {
      expect(handle(container, `polygon-vertex-${i}`)).toBeTruthy();
      expect(handle(container, `polygon-edge-${i}`)).toBeTruthy();
    }
    expect(lastAnchors()).toEqual([]);
  });

  it('hides the rotate handle too, not just the resize anchors (S5 review)', () => {
    render(<TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />);

    enterEditPoints();

    expect(lastRotateEnabled()).toBe(false);
  });

  it('Enter toggles edit-points mode on the current selection', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );

    selectShape();
    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();

    fireEvent.keyDown(window, { key: 'Enter' });
    expect(handle(container, 'polygon-vertex-0')).toBeTruthy();
    expect(lastAnchors()).toEqual([]);

    fireEvent.keyDown(window, { key: 'Enter' });
    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();
    expect(lastAnchors()).toEqual(FULL_ANCHORS);
  });

  it('does nothing while a button elsewhere on the page has focus (review nit)', () => {
    const outsideButton = document.createElement('button');
    document.body.appendChild(outsideButton);
    outsideButton.focus();

    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    // A Tab-focused Save/Publish button firing its OWN native Enter-click
    // must not ALSO be intercepted into edit-points mode just because a
    // polygon happens to be selected underneath it.
    fireEvent.keyDown(window, { key: 'Enter' });

    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();
    document.body.removeChild(outsideButton);
  });

  it('the Inspector "Edit points" button enters the same mode', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );

    selectShape();
    fireEvent.click(screen.getByRole('button', { name: 'Edit points' }));

    expect(handle(container, 'polygon-vertex-0')).toBeTruthy();
    expect(lastAnchors()).toEqual([]);
    // The button itself flips label once inside the mode.
    expect(screen.getByRole('button', { name: 'Done editing points' })).toBeInTheDocument();
  });

  it('gives a boxed price badge the same edit-points mode (AC-S5-4)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(boxedBadge('sh1'))} onChange={vi.fn()} />,
    );

    enterEditPoints();

    expect(handle(container, 'polygon-vertex-0')).toBeTruthy();
    expect(lastAnchors()).toEqual([]);
  });

  it('a rectangle offers neither mode change - a second click is just a click (no points to edit)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'rect'))} onChange={vi.fn()} />,
    );

    enterEditPoints();

    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();
    expect(lastAnchors()).toEqual(FULL_ANCHORS);
  });

  it('a locked polygon offers neither mode (AC-S5-5)', () => {
    const { container } = render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('sh1', 'polygon', {}, { locked: true }))}
        onChange={vi.fn()}
      />,
    );

    // A locked layer cannot even be entered into single-selection by click in
    // the real editor (marquee/click ignore locked layers upstream of this
    // guard); asserting the mode itself never arms is the contract this file
    // owns - `cornerHandleLayer`'s guard reads `layer.locked` directly.
    fireEvent.doubleClick(screen.getByTestId('layer-sh1'));
    fireEvent.keyDown(window, { key: 'Enter' });

    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();
  });

  it('a hidden polygon offers neither mode (AC-S5-5)', () => {
    const { container } = render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('sh1', 'polygon', {}, { visible: false }))}
        onChange={vi.fn()}
      />,
    );

    fireEvent.doubleClick(screen.getByTestId('layer-sh1'));
    fireEvent.keyDown(window, { key: 'Enter' });

    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Leaving edit-points mode (AC-S5-3)
// ---------------------------------------------------------------------------

describe('leaving edit-points mode (S5, AC-S5-3)', () => {
  it('Esc returns to select mode, keeping the shape selected', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );

    enterEditPoints();
    expect(handle(container, 'polygon-vertex-0')).toBeTruthy();

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();
    // Selection survives - the Transformer's full anchor set is back, not
    // Escape's OTHER job (deselect), which only runs once there is no mode
    // left to step out of.
    expect(lastAnchors()).toEqual(FULL_ANCHORS);
  });

  it('Enter (again) returns to select mode', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );

    enterEditPoints();
    fireEvent.keyDown(window, { key: 'Enter' });

    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();
    expect(lastAnchors()).toEqual(FULL_ANCHORS);
  });

  it('selecting a different layer exits edit-points mode for the first one', () => {
    const { container } = render(
      <TagCanvasEditor
        doc={docWith(
          shapeLayer('sh1', 'polygon'),
          shapeLayer('sh2', 'rect', {}, { x_mm: 45 }),
        )}
        onChange={vi.fn()}
      />,
    );

    enterEditPoints('sh1');
    expect(handle(container, 'polygon-vertex-0')).toBeTruthy();

    fireEvent.click(screen.getByTestId('layer-sh2'));

    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();
  });

  it('re-selecting the SAME polygon with a single click after straying elsewhere shows Transformer anchors, not vertex handles (B2)', () => {
    // The review's exact repro is click-empty-canvas then re-click the same
    // polygon; the Stage stand-in's `getPointerPosition` always returns
    // null, so a literal mousedown/mouseup click-empty sequence cannot run
    // through it here. Selecting sh2 (a rect, ineligible for corner
    // handles) exercises the identical underlying condition: cornerHandleLayer
    // stops matching the stale editingPointsId - a plain single click back
    // onto sh1 must not land back in edit-points mode just because that
    // stale id was never cleared (B2).
    const { container } = render(
      <TagCanvasEditor
        doc={docWith(
          shapeLayer('sh1', 'polygon'),
          shapeLayer('sh2', 'rect', {}, { x_mm: 45 }),
        )}
        onChange={vi.fn()}
      />,
    );

    enterEditPoints('sh1');
    expect(handle(container, 'polygon-vertex-0')).toBeTruthy();

    fireEvent.click(screen.getByTestId('layer-sh2'));
    selectShape('sh1');

    expect(queryHandle(container, 'polygon-vertex-0')).toBeNull();
    expect(lastAnchors()).toEqual(FULL_ANCHORS);
  });
});

// ---------------------------------------------------------------------------
// Geometry inside edit-points mode (r5 S1 Shift-lock behaviour, unchanged -
// only how the mode is ENTERED moved, in the describe blocks above).
// ---------------------------------------------------------------------------

describe('edit-points mode geometry (r4b/r5, now behind double-click/Enter)', () => {
  it('dragging a corner writes the new normalized point, and only that one (AC-S4-2)', () => {
    const onChange = vi.fn();
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={onChange} />,
    );
    enterEditPoints();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseUp(vertex, { clientX: W_PX / 2, clientY: 0 });

    expect(pointsOf()).toEqual([
      { x: 0, y: 0 },
      { x: 0.5, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ]);

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const saved = onChange.mock.calls.at(-1)?.[0] as TagTemplateDoc;
    const savedProps = saved.layers[0].props;
    expect(savedProps.kind === 'shape' ? savedProps.points : null).toEqual([
      { x: 0, y: 0 },
      { x: 0.5, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ]);
  });

  it('follows the cursor while the corner is still being dragged', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: W_PX / 4, clientY: 0 });

    expect(pointsOf()[1]).toEqual({ x: 0.25, y: 0 });
  });

  it('GROWS the box when a corner is dragged past its right wall (AC-S4-11)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseUp(vertex, { clientX: 180, clientY: 0 });

    expect(boxOf()).toEqual({ x: 0, y: 0, width: 60, height: 20 });
    expect(pointsOf()).toEqual([
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 0.666667, y: 1 },
      { x: 0, y: 1 },
    ]);
  });

  it('moves the layer origin when the growth is off the left wall (AC-S4-11)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    const vertex = handle(container, 'polygon-vertex-0');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseUp(vertex, { clientX: -60, clientY: 0 });

    expect(boxOf()).toEqual({ x: -20, y: 0, width: 60, height: 20 });
    expect(pointsOf()[0]).toEqual({ x: 0, y: 0 });
    expect(pointsOf()[3]).toEqual({ x: 0.333333, y: 1 });
    expect(konva.positions.at(-1)).toEqual({ x: 0, y: 0 });
  });

  it('snaps a dragged EDGE handle back onto the recomputed midpoint', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    const edge = handle(container, 'polygon-edge-0');
    fireEvent.mouseDown(edge);
    fireEvent.mouseUp(edge, { clientX: W_PX / 2, clientY: -90 });

    expect(boxOf()).toEqual({ x: 0, y: -30, width: 40, height: 50 });
    expect(konva.positions.at(-1)).toEqual({ x: W_PX / 2, y: 0 });
  });

  it('dragging an edge midpoint moves both of its endpoints (AC-S4-2)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    const edge = handle(container, 'polygon-edge-0');
    fireEvent.mouseDown(edge);
    fireEvent.mouseUp(edge, { clientX: W_PX / 2, clientY: H_PX / 2 });

    expect(boxOf()).toEqual({ x: 0, y: 10, width: 40, height: 10 });
    expect(pointsOf()).toEqual([
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ]);
  });

  it('Shift snaps a corner drag to the dominant axis (r5 S1)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: 140, clientY: 3, shiftKey: true });

    expect(konva.positions.at(-1)).toEqual({ x: 140, y: 0 });
  });

  it('Shift snaps a corner drag to the diagonal when the deltas are close (r5 S1)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: 130, clientY: 12, shiftKey: true });

    expect(konva.positions.at(-1)).toEqual({ x: 131, y: 11 });
  });

  it('frees the corner once Shift is released mid-drag (r5 S1)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: 140, clientY: 3, shiftKey: true });
    expect(konva.positions.at(-1)).toEqual({ x: 140, y: 0 });
    const pushedWhileLocked = konva.positions.length;

    fireEvent.mouseMove(vertex, { clientX: 150, clientY: 4 });
    expect(konva.positions.length).toBe(pushedWhileLocked);
    expect(pointsOf()[1]).toEqual({ x: 1.25, y: 4 / 60 });
  });

  it('Shift constrains an EDGE drag to its dominant axis too (r5 S1)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    const edge = handle(container, 'polygon-edge-0');
    fireEvent.mouseDown(edge);
    fireEvent.mouseMove(edge, { clientX: 80, clientY: 3, shiftKey: true });

    expect(konva.positions.at(-1)).toEqual({ x: 80, y: 0 });
  });

  it('gives a boxed price badge the same handles once in edit-points mode (r4b, AC-S6-2)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(boxedBadge('sh1'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    expect(handle(container, 'polygon-vertex-2').getAttribute('data-x')).toBe(String(W_PX));
    expect(lastAnchors()).toEqual([]);

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseUp(vertex, { clientX: 180, clientY: 0 });

    expect(boxOf()).toEqual({ x: 0, y: 0, width: 60, height: 20 });
  });

  it('never strands a drag preview when the handles disappear mid-drag (r4c)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: W_PX / 4, clientY: 0 });
    expect(pointsOf()[1]).toEqual({ x: 0.25, y: 0 });

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(container.querySelector('[data-name="polygon-vertex-0"]')).toBeNull();

    enterEditPoints();

    expect(pointsOf()).toEqual([
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ]);
  });

  /**
   * r4d: Escape CANCELS the drag, it does not commit half of it. Escape's
   * FIRST job now is dropping edit-points mode (S5) - the in-flight drag is
   * cancelled ahead of that, in the same keydown, so this still holds.
   */
  it('Escape mid-drag cancels it: nothing committed, nothing to undo (r4d)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    const before = boxOf();
    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: 180, clientY: 0 });

    // The FIRST Escape here only drops edit-points mode back to select -
    // the handles unmount, and the stand-in fires the `dragend` Konva fires
    // on a node destroyed mid-drag, which must still commit nothing.
    fireEvent.keyDown(window, { key: 'Escape' });

    expect(boxOf()).toEqual(before);
    expect(pointsOf()).toEqual([
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ]);
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
  });

  it('releasing after an Escape still commits nothing (r4d)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    const before = boxOf();
    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: 180, clientY: 0 });
    fireEvent.keyDown(window, { key: 'Escape' });
    fireEvent.mouseUp(vertex, { clientX: 180, clientY: 0 });

    expect(boxOf()).toEqual(before);
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
  });

  it('one drag is one undo (AC-S4-7)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('sh1', 'polygon'))} onChange={vi.fn()} />,
    );
    enterEditPoints();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseUp(vertex, { clientX: 180, clientY: 0 });
    expect(boxOf().width).toBe(60);

    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });

    expect(boxOf().width).toBe(40);
    expect(pointsOf()[1]).toEqual({ x: 1, y: 0 });
  });
});
