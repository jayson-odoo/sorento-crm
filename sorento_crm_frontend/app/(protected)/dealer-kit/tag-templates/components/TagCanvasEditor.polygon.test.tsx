/**
 * Free-corner polygon editing on the canvas (S4, AC-S4-2/7; r4b AC-S4-10/11).
 *
 * The geometry itself is pinned in `lib/dealer-kit/polygon-path.test.ts`.
 * This is the WIRING: SELECTING a polygon puts a handle on every corner and
 * every edge midpoint (r4b - the first cut hid them behind a double-click and
 * the user, having picked Polygon and dragged, saw nothing at all), the
 * Transformer gives up its resize anchors so they cannot sit on top of those
 * handles, a drag commits ONE new set of normalized points plus the box that
 * now contains them, and deselecting takes the handles away again.
 *
 * Konva does not run in jsdom, so `react-konva` is stood in for by divs that
 * carry the props a handle is identified and driven by - the same pattern
 * `TagCanvasEditor.guides.test.tsx` uses for a ruler guide's `stroke`. A
 * Konva drag reports the node's position through `e.target.x()/y()`, so the
 * stand-in turns the press / move / release it is driven by into exactly
 * that, and records `position()` so the drag-end snap-back can be asserted.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { polygonPoints } from '@/lib/dealer-kit/polygon-path';

// -- Stand-ins ---------------------------------------------------------------

/** What the stand-in records for the test, hoisted with the mock factory. */
const konva = vi.hoisted(() => ({
  positions: [] as { x: number; y: number }[],
  anchors: [] as unknown[],
}));

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
  // through, the same one Konva's own `evt` would carry (S1).
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
      // at the position the pointer had reached. That is the whole of the
      // Escape defect (r4d), so the stand-in has to do it too - held in a ref
      // and fired from the unmount cleanup, exactly where Konva fires it.
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

  return {
    Stage: passthrough('stage'),
    Layer: passthrough('layer'),
    Group: draggable('group'),
    Rect: draggable('rect'),
    Circle: draggable('circle'),
    Line: passthrough('line'),
    Transformer: function TransformerStandIn(props: { enabledAnchors?: unknown[] }) {
      konva.anchors.push(props.enabledAnchors);
      return <div data-konva="transformer" data-anchors={JSON.stringify(props.enabledAnchors)} />;
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
  }) => (
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

// -- The document under test --------------------------------------------------

/**
 * 40mm x 20mm at the origin. The stage is never measured in jsdom, so the
 * view stays at zoom 1 and `CANVAS_PX_PER_MM` (3) is the whole scale: the
 * layer box is 120 x 60 px and every handle position below is exact.
 */
const W_PX = 120;
const H_PX = 60;

function shapeLayer(shape: 'polygon' | 'rect', extra: Record<string, unknown> = {}): TagLayer {
  return {
    id: 'sh1',
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
  } as TagLayer;
}

function docWith(layer: TagLayer): TagTemplateDoc {
  return { width_mm: 60, height_mm: 40, layers: [layer] };
}

function handle(container: HTMLElement, name: string) {
  const element = container.querySelector(`[data-name="${name}"]`);
  if (!element) throw new Error(`no handle named ${name}`);
  return element as HTMLElement;
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

/** Selection is all it takes now (r4b, AC-S4-10). */
function selectShape() {
  fireEvent.click(screen.getByTestId('layer-sh1'));
}

function lastAnchors() {
  return konva.anchors.at(-1);
}

describe('TagCanvasEditor polygon corner handles (S4, r4b)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    konva.positions.length = 0;
    konva.anchors.length = 0;
  });

  it('SELECTING a polygon shows a handle on every corner and every edge (AC-S4-10)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );

    expect(container.querySelector('[data-name="polygon-vertex-0"]')).toBeNull();

    selectShape();

    for (let i = 0; i < 4; i += 1) {
      expect(handle(container, `polygon-vertex-${i}`)).toBeTruthy();
      expect(handle(container, `polygon-edge-${i}`)).toBeTruthy();
    }
    // Corner 2 is the bottom right of the box; edge 0 runs along the top.
    expect(handle(container, 'polygon-vertex-2').getAttribute('data-x')).toBe(String(W_PX));
    expect(handle(container, 'polygon-vertex-2').getAttribute('data-y')).toBe(String(H_PX));
    expect(handle(container, 'polygon-edge-0').getAttribute('data-x')).toBe(String(W_PX / 2));
    expect(handle(container, 'polygon-edge-0').getAttribute('data-y')).toBe('0');
  });

  it('gives the Transformer no box anchors while a polygon is selected (AC-S4-10)', () => {
    render(<TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />);

    expect(lastAnchors()).toEqual(expect.arrayContaining(['top-left']));

    selectShape();

    // Empty, not absent: react-konva keeps the rotater, which is the one grip
    // a polygon still wants.
    expect(lastAnchors()).toEqual([]);
  });

  it('a double-click is harmless - it just selects, same as the click', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );

    fireEvent.doubleClick(screen.getByTestId('layer-sh1'));

    expect(handle(container, 'polygon-vertex-0')).toBeTruthy();
  });

  it('leaves a rectangle alone - only a polygon has corners to edit', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('rect'))} onChange={vi.fn()} />,
    );

    selectShape();

    expect(container.querySelector('[data-name="polygon-vertex-0"]')).toBeNull();
    expect(lastAnchors()).toEqual(expect.arrayContaining(['top-left']));
  });

  it('dragging a corner writes the new normalized point, and only that one (AC-S4-2)', () => {
    const onChange = vi.fn();
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={onChange} />,
    );
    selectShape();

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
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: W_PX / 4, clientY: 0 });

    expect(pointsOf()[1]).toEqual({ x: 0.25, y: 0 });
  });

  it('GROWS the box when a corner is dragged past its right wall (AC-S4-11)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    // 180px is 60mm: 20mm past the 40mm box.
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
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    const vertex = handle(container, 'polygon-vertex-0');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseUp(vertex, { clientX: -60, clientY: 0 });

    expect(boxOf()).toEqual({ x: -20, y: 0, width: 60, height: 20 });
    expect(pointsOf()[0]).toEqual({ x: 0, y: 0 });
    expect(pointsOf()[3]).toEqual({ x: 0.333333, y: 1 });
    // The handle itself was dropped at -60px, in the OLD box's coordinates.
    // Without this it would strand out in the margin while the corner it
    // stands for had already moved to the new box's origin.
    expect(konva.positions.at(-1)).toEqual({ x: 0, y: 0 });
  });

  it('snaps a dragged EDGE handle back onto the recomputed midpoint', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    // Edge 0 is the top edge; its midpoint starts at (60, 0). Drag it 30mm
    // (90px) up, so the whole box moves up and the midpoint is back at y 0.
    const edge = handle(container, 'polygon-edge-0');
    fireEvent.mouseDown(edge);
    fireEvent.mouseUp(edge, { clientX: W_PX / 2, clientY: -90 });

    expect(boxOf()).toEqual({ x: 0, y: -30, width: 40, height: 50 });
    expect(konva.positions.at(-1)).toEqual({ x: W_PX / 2, y: 0 });
  });

  it('dragging an edge midpoint moves both of its endpoints (AC-S4-2)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    // Edge 0 is the top edge; its midpoint starts at (60, 0). Half the box
    // down leaves the shape in the bottom half, so the box refits to it.
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

  it('Shift snaps a corner drag to the dominant axis (S1, AC-S1-1)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    // Vertex 1 (top right) starts at (120, 0). dx=20, dy=3: the ratio is well
    // under tan(22.5deg), so the corner is pinned to the dominant (x) axis -
    // the raw y of 3 never reaches the shape.
    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: 140, clientY: 3, shiftKey: true });

    expect(konva.positions.at(-1)).toEqual({ x: 140, y: 0 });
  });

  it('Shift snaps a corner drag to the diagonal when the deltas are close (S1, AC-S1-1)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    // dx=10, dy=12: close enough to 45 degrees that both land on the average
    // magnitude, 11, rather than either raw value.
    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: 130, clientY: 12, shiftKey: true });

    expect(konva.positions.at(-1)).toEqual({ x: 131, y: 11 });
  });

  it('frees the corner once Shift is released mid-drag (S1, AC-S1-2)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: 140, clientY: 3, shiftKey: true });
    expect(konva.positions.at(-1)).toEqual({ x: 140, y: 0 });
    const pushedWhileLocked = konva.positions.length;

    // Shift comes up: the handler no longer overrides the node's position,
    // so nothing new is pushed and the corner follows the raw cursor.
    fireEvent.mouseMove(vertex, { clientX: 150, clientY: 0 });
    expect(konva.positions.length).toBe(pushedWhileLocked);
    expect(pointsOf()[1]).toEqual({ x: 1.25, y: 0 });
  });

  it('Shift constrains an EDGE drag to its dominant axis too (S1, AC-S1-3)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    // Edge 0's midpoint starts at (60, 0), same dx/dy as the first corner
    // case above.
    const edge = handle(container, 'polygon-edge-0');
    fireEvent.mouseDown(edge);
    fireEvent.mouseMove(edge, { clientX: 80, clientY: 3, shiftKey: true });

    expect(konva.positions.at(-1)).toEqual({ x: 80, y: 0 });
  });

  it('gives a boxed price badge the same handles (r4b, AC-S6-2)', () => {
    const badge = {
      id: 'sh1',
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

    const { container } = render(<TagCanvasEditor doc={docWith(badge)} onChange={vi.fn()} />);
    selectShape();

    expect(handle(container, 'polygon-vertex-2').getAttribute('data-x')).toBe(String(W_PX));
    expect(lastAnchors()).toEqual([]);

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseUp(vertex, { clientX: 180, clientY: 0 });

    expect(boxOf()).toEqual({ x: 0, y: 0, width: 60, height: 20 });
  });

  it('leaves an unboxed price badge alone - it has no callout to shape', () => {
    const badge = {
      id: 'sh1',
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
      },
    } as unknown as TagLayer;

    const { container } = render(<TagCanvasEditor doc={docWith(badge)} onChange={vi.fn()} />);
    selectShape();

    expect(container.querySelector('[data-name="polygon-vertex-0"]')).toBeNull();
    expect(lastAnchors()).toEqual(expect.arrayContaining(['top-left']));
  });

  it('deselecting takes the handles away (AC-S4-7)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();
    expect(container.querySelector('[data-name="polygon-vertex-0"]')).toBeTruthy();

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(container.querySelector('[data-name="polygon-vertex-0"]')).toBeNull();
  });

  it('never strands a drag preview when the handles disappear mid-drag (r4c)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: W_PX / 4, clientY: 0 });
    // Sanity check: the preview IS showing the dragged point before Escape.
    expect(pointsOf()[1]).toEqual({ x: 0.25, y: 0 });

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(container.querySelector('[data-name="polygon-vertex-0"]')).toBeNull();

    selectShape();

    expect(pointsOf()).toEqual([
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ]);
  });

  /**
   * r4d: Escape CANCELS the drag, it does not commit half of it.
   *
   * Measured on the request designer: press a corner, move, press Escape, and
   * the box refitted around wherever the pointer had got to (W 33.2 -> 52.54),
   * the shape kept the half-drag and the designer autosaved it. The handles
   * unmount on the Escape, and Konva still delivers that node's `dragend`, so
   * the commit path ran on a drag the user had just abandoned.
   */
  it('Escape mid-drag cancels it: nothing committed, nothing to undo (r4d)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    const before = boxOf();
    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: 180, clientY: 0 });

    // The handles unmount here, and the stand-in fires the `dragend` Konva
    // fires on a node destroyed mid-drag.
    fireEvent.keyDown(window, { key: 'Escape' });

    expect(boxOf()).toEqual(before);
    expect(pointsOf()).toEqual([
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ]);
    // No history entry either: an abandoned drag is not a step to undo.
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
  });

  it('releasing after an Escape still commits nothing (r4d)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    const before = boxOf();
    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: 180, clientY: 0 });
    fireEvent.keyDown(window, { key: 'Escape' });
    // The button comes up after the handle has gone; Konva reports it against
    // the node it was dragging, which no longer exists.
    fireEvent.mouseUp(vertex, { clientX: 180, clientY: 0 });

    expect(boxOf()).toEqual(before);
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
  });

  it('one drag is one undo (AC-S4-7)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    selectShape();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseUp(vertex, { clientX: 180, clientY: 0 });
    expect(boxOf().width).toBe(60);

    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });

    expect(boxOf().width).toBe(40);
    expect(pointsOf()[1]).toEqual({ x: 1, y: 0 });
  });
});
