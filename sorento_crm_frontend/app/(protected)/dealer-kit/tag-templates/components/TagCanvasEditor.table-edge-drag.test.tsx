/**
 * SPEC-SHEET-PARITY-B2 v3 editor, AC-C5.1: on a SELECTED table, dragging a row's bottom edge (inner
 * boundary or the table's bottom) sets that row's `height_mm`; dragging an inner column boundary
 * moves width from the right-hand neighbour to the left column (the total, so the table width,
 * stays). Min row 2 mm, min column 5 mm. One drag is one Undo step: nothing is written until the
 * pointer is released. Shared `TagCanvasEditor`, so the same on a spec sheet page (embedded).
 * Written test-FIRST.
 *
 * Hit strips: `table-row-edge-<row>` (the bottom edge of that row) and `table-col-edge-<col>` (the
 * right edge of that column, inner boundaries only).
 */
import * as React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { CANVAS_PX_PER_MM } from '@/lib/dealer-kit/canvas-geometry';

const pointer = vi.hoisted(() => ({ x: 0, y: 0 }));

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
      ref?: React.Ref<{ getContent: () => HTMLElement; getPointerPosition: () => { x: number; y: number } }>;
    }) => {
      const instance = {
        getContent: () => document.createElement('div'),
        getPointerPosition: () => ({ x: pointer.x, y: pointer.y }),
      };
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
  KonvaTagLayer: ({ layer, onSelect }: { layer: { id: string }; onSelect?: (id: string, additive: boolean) => void }) => (
    <div data-testid={`layer-${layer.id}`} onClick={() => onSelect?.(layer.id, false)} />
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

import { TagCanvasEditor, type EmbeddedMode } from './TagCanvasEditor';

type TableShape = { rows: { height_mm: number }[]; columns: { width_mm: number }[] };

/** 3 rows x 2 columns at (5, 5): columns 30 mm, rows 6 mm, short text (no row grows). */
function tableLayer(extra: Partial<TagLayer> = {}): TagLayer {
  const side = { color: '#000000', width_mm: 0.2 };
  const texts = [
    ['A', 'B'],
    ['C', 'D'],
    ['E', 'F'],
  ];
  return {
    id: 'tbl',
    type: 'table',
    x_mm: 5,
    y_mm: 5,
    width_mm: 60,
    height_mm: 18,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'table',
      columns: [{ width_mm: 30 }, { width_mm: 30 }],
      rows: texts.map(() => ({ height_mm: 6 })),
      cells: texts.map((row) =>
        row.map((text) => ({ text, padding_mm: 1, border: { top: side, right: side, bottom: side, left: side } })),
      ),
      fontFamily: 'DM Sans',
      // 8 pt: one line plus padding is under 6 mm, so no row grows past its set height.
      fontSize: 8,
      color: '#000000',
      align: 'left',
      verticalAlign: 'middle',
    },
    ...extra,
  } as unknown as TagLayer;
}

const tableOf = (layers: TagLayer[]) => layers.find((l) => l.id === 'tbl')!.props as unknown as TableShape;

function renderDesigner(layer: TagLayer = tableLayer()) {
  const latest: { layers: TagLayer[] } = { layers: [layer] };
  render(
    <TagCanvasEditor
      doc={{ width_mm: 80, height_mm: 60, layers: [layer] }}
      onChange={vi.fn()}
      onLayersChange={(next) => {
        latest.layers = next;
      }}
    />,
  );
  return latest;
}

function selectTable() {
  pointer.x = 15 * CANVAS_PX_PER_MM;
  pointer.y = 8 * CANVAS_PX_PER_MM;
  fireEvent.click(screen.getByTestId('layer-tbl'));
}

/** Drag a hit strip by (dx, dy) millimetres at `pxPerMm`, released at the end unless `release` is false. */
function drag(strip: HTMLElement, dx_mm: number, dy_mm: number, pxPerMm = CANVAS_PX_PER_MM, release = true) {
  const start = { clientX: 200, clientY: 200, pointerId: 1, button: 0 };
  const end = { clientX: 200 + dx_mm * pxPerMm, clientY: 200 + dy_mm * pxPerMm, pointerId: 1, button: 0 };
  fireEvent.pointerDown(strip, start);
  fireEvent.pointerMove(strip, { ...start, clientX: (start.clientX + end.clientX) / 2, clientY: (start.clientY + end.clientY) / 2 });
  fireEvent.pointerMove(strip, end);
  if (release) fireEvent.pointerUp(strip, end);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('row height by dragging a row edge (AC-C5.1)', () => {
  it('no edge strips until the table is selected', () => {
    renderDesigner();
    expect(screen.queryByTestId('table-row-edge-0')).toBeNull();
    selectTable();
    expect(screen.getByTestId('table-row-edge-0')).toBeInTheDocument();
    expect(screen.getByTestId('table-row-edge-2')).toBeInTheDocument();
  });

  it('dragging an inner row boundary down sets that row height_mm, and only that row', () => {
    const latest = renderDesigner();
    selectTable();
    drag(screen.getByTestId('table-row-edge-0'), 0, 4);
    expect(tableOf(latest.layers).rows.map((r) => r.height_mm)).toEqual([10, 6, 6]);
  });

  it('the bottom edge of the table sets the last row (a tall empty row)', () => {
    const latest = renderDesigner();
    selectTable();
    drag(screen.getByTestId('table-row-edge-2'), 0, 20);
    expect(tableOf(latest.layers).rows.map((r) => r.height_mm)).toEqual([6, 6, 26]);
  });

  it('a row never goes below 2 mm', () => {
    const latest = renderDesigner();
    selectTable();
    drag(screen.getByTestId('table-row-edge-1'), 0, -30);
    expect(tableOf(latest.layers).rows[1].height_mm).toBe(2);
  });

  it('nothing is written while dragging; the drag is one Undo step', () => {
    const latest = renderDesigner();
    selectTable();
    const strip = screen.getByTestId('table-row-edge-0');
    drag(strip, 0, 4, CANVAS_PX_PER_MM, false);
    expect(tableOf(latest.layers).rows[0].height_mm).toBe(6);
    fireEvent.pointerUp(strip, { clientX: 200, clientY: 200 + 4 * CANVAS_PX_PER_MM, pointerId: 1, button: 0 });
    expect(tableOf(latest.layers).rows[0].height_mm).toBe(10);
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(tableOf(latest.layers).rows[0].height_mm).toBe(6);
  });
});

describe('column width by dragging an inner column boundary (AC-C5.1)', () => {
  it('the right-hand neighbour gives up the width; the table total stays', () => {
    const latest = renderDesigner();
    selectTable();
    drag(screen.getByTestId('table-col-edge-0'), 5, 0);
    expect(tableOf(latest.layers).columns.map((c) => c.width_mm)).toEqual([35, 25]);
  });

  it('neither column goes below 5 mm', () => {
    const latest = renderDesigner();
    selectTable();
    drag(screen.getByTestId('table-col-edge-0'), 40, 0);
    expect(tableOf(latest.layers).columns.map((c) => c.width_mm)).toEqual([55, 5]);
    drag(screen.getByTestId('table-col-edge-0'), -80, 0);
    expect(tableOf(latest.layers).columns.map((c) => c.width_mm)).toEqual([5, 55]);
  });

  it('only inner boundaries: no strip on the table right edge', () => {
    renderDesigner();
    selectTable();
    expect(screen.getByTestId('table-col-edge-0')).toBeInTheDocument();
    expect(screen.queryByTestId('table-col-edge-1')).toBeNull();
  });
});

describe('locked table', () => {
  it('a locked table offers no edge strips', () => {
    renderDesigner(tableLayer({ locked: true }));
    selectTable();
    expect(screen.queryByTestId('table-row-edge-0')).toBeNull();
    expect(screen.queryByTestId('table-col-edge-0')).toBeNull();
  });
});

describe('spec sheet page (embedded): the same edge drag', () => {
  function Page({ latest }: { latest: { layers: TagLayer[] } }) {
    const [selected, setSelected] = React.useState<string | null>('tbl');
    const embedded: EmbeddedMode = {
      pxPerMm: 2,
      selectedLayerId: selected,
      onSelect: setSelected,
      controllerRef: { current: null },
      active: true,
      readOnly: false,
    };
    return (
      <TagCanvasEditor
        doc={{ width_mm: 100, height_mm: 60, layers: [tableLayer()] } as TagTemplateDoc}
        onChange={vi.fn()}
        docId="sheet:k1"
        specSheet
        embedded={embedded}
        onLayersChange={(next) => {
          latest.layers = next;
        }}
      />
    );
  }

  it('dragging a row edge on a page sets the row height', () => {
    const latest: { layers: TagLayer[] } = { layers: [] };
    render(<Page latest={latest} />);
    drag(screen.getByTestId('table-row-edge-1'), 0, 3, 2);
    expect(tableOf(latest.layers).rows.map((r) => r.height_mm)).toEqual([6, 9, 6]);
  });

  it('a read-only page offers no edge strips', () => {
    function ReadOnlyPage() {
      const embedded: EmbeddedMode = {
        pxPerMm: 2,
        selectedLayerId: 'tbl',
        onSelect: () => undefined,
        controllerRef: { current: null },
        active: false,
        readOnly: true,
      };
      return (
        <TagCanvasEditor
          doc={{ width_mm: 100, height_mm: 60, layers: [tableLayer()] } as TagTemplateDoc}
          onChange={vi.fn()}
          docId="sheet:k1"
          specSheet
          embedded={embedded}
        />
      );
    }
    render(<ReadOnlyPage />);
    expect(screen.queryByTestId('table-row-edge-0')).toBeNull();
  });
});
