/**
 * Free-corner polygon editing on the canvas (S4, AC-S4-2/3/7).
 *
 * The geometry itself is pinned in `lib/dealer-kit/polygon-path.test.ts`.
 * This is the WIRING: a double-click puts the layer into corner editing,
 * every corner and every edge midpoint gets a handle, a drag commits ONE new
 * set of normalized points, and Escape leaves again.
 *
 * Konva does not run in jsdom, so `react-konva` is stood in for by divs that
 * carry the props a handle is identified and driven by - the same pattern
 * `TagCanvasEditor.guides.test.tsx` uses for a ruler guide's `stroke`. A
 * Konva drag reports the node's position through `e.target.x()/y()`, so the
 * stand-in turns the press / move / release it is driven by into exactly
 * that.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { polygonPoints } from '@/lib/dealer-kit/polygon-path';

// -- Stand-ins ---------------------------------------------------------------

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
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
    onDragMove?: (e: { target: { x: () => number; y: () => number } }) => void;
    onDragEnd?: (e: { target: { x: () => number; y: () => number } }) => void;
  }

  // A Konva drag hands the handler the NODE; everything this component reads
  // off it is its position, so the stand-in answers the pointer's own client
  // coordinates. Press / move / release stands in for the drag itself: jsdom
  // has no DragEvent that carries coordinates, and Konva's drag is built out
  // of these three anyway.
  const dragged = (event: { clientX: number; clientY: number }) => ({
    target: { x: () => event.clientX, y: () => event.clientY },
  });

  const draggable = (kind: string) =>
    function KonvaDraggableStandIn(props: HandleProps) {
      return (
        <div
          data-konva={kind}
          data-name={props.name}
          data-x={props.x}
          data-y={props.y}
          onMouseDown={(e) => props.onDragStart?.(dragged(e))}
          onMouseMove={(e) => props.onDragMove?.(dragged(e))}
          onMouseUp={(e) => props.onDragEnd?.(dragged(e))}
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
    Transformer: passthrough('transformer'),
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

function enterCornerEditing() {
  fireEvent.doubleClick(screen.getByTestId('layer-sh1'));
}

describe('TagCanvasEditor polygon corner editing (S4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('double-clicking a polygon shows a handle on every corner and every edge (AC-S4-2)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );

    expect(container.querySelector('[data-name="polygon-vertex-0"]')).toBeNull();

    enterCornerEditing();

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

  it('leaves a rectangle alone - only a polygon has corners to edit', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('rect'))} onChange={vi.fn()} />,
    );

    fireEvent.doubleClick(screen.getByTestId('layer-sh1'));

    expect(container.querySelector('[data-name="polygon-vertex-0"]')).toBeNull();
  });

  it('dragging a corner writes the new normalized point, and only that one (AC-S4-2)', () => {
    const onChange = vi.fn();
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={onChange} />,
    );
    enterCornerEditing();

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
    enterCornerEditing();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseMove(vertex, { clientX: W_PX / 4, clientY: 0 });

    expect(pointsOf()[1]).toEqual({ x: 0.25, y: 0 });
  });

  it('keeps a dragged corner inside the layer box (AC-S4-3)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    enterCornerEditing();

    const vertex = handle(container, 'polygon-vertex-0');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseUp(vertex, { clientX: -400, clientY: 400 });

    expect(pointsOf()[0]).toEqual({ x: 0, y: 1 });
  });

  it('dragging an edge midpoint moves both of its endpoints (AC-S4-2)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    enterCornerEditing();

    // Edge 0 is the top edge; its midpoint starts at (60, 0).
    const edge = handle(container, 'polygon-edge-0');
    fireEvent.mouseDown(edge);
    fireEvent.mouseUp(edge, { clientX: W_PX / 2, clientY: H_PX / 2 });

    expect(pointsOf()).toEqual([
      { x: 0, y: 0.5 },
      { x: 1, y: 0.5 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ]);
  });

  it('Escape leaves corner editing (AC-S4-7)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    enterCornerEditing();
    expect(container.querySelector('[data-name="polygon-vertex-0"]')).toBeTruthy();

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(container.querySelector('[data-name="polygon-vertex-0"]')).toBeNull();
  });

  it('one drag is one undo (AC-S4-7)', () => {
    const { container } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('polygon'))} onChange={vi.fn()} />,
    );
    enterCornerEditing();

    const vertex = handle(container, 'polygon-vertex-1');
    fireEvent.mouseDown(vertex);
    fireEvent.mouseUp(vertex, { clientX: W_PX / 2, clientY: 0 });
    expect(pointsOf()[1]).toEqual({ x: 0.5, y: 0 });

    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });

    expect(pointsOf()[1]).toEqual({ x: 1, y: 0 });
  });
});
