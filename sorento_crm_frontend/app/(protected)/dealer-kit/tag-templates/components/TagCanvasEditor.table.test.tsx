/**
 * SPEC-SHEET-DESIGNER-PARITY B4: the designer adds a Table (price tag AND spec sheet templates) and
 * offers the table row / column / merge actions on right-click. Written test-FIRST.
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

/** A 2-column table fixture written out here so this file does not depend on the layout module. */
function tableProps(rows: number, cols: number, width: number) {
  const side = { color: '#000000', width_mm: 0.2 };
  const blank = () => ({ text: '', padding_mm: 1, border: { top: side, right: side, bottom: side, left: side } });
  return {
    kind: 'table' as const,
    columns: Array.from({ length: cols }, () => ({ width_mm: width / cols })),
    rows: Array.from({ length: rows }, () => ({ height_mm: 6 })),
    cells: Array.from({ length: rows }, () => Array.from({ length: cols }, blank)),
    fontFamily: 'DM Sans',
    fontSize: 10,
    color: '#000000',
    align: 'left',
    verticalAlign: 'middle',
  };
}

function tableLayer(id: string): TagLayer {
  return {
    id,
    type: 'table',
    x_mm: 5,
    y_mm: 5,
    width_mm: 60,
    height_mm: 30,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: tableProps(3, 2, 60),
  } as unknown as TagLayer;
}

describe('adding a table', () => {
  it.each([false, true])('the Table toolbar action adds a 3 x 2 table layer (specSheet=%s)', (specSheet) => {
    let latest: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={{ width_mm: 80, height_mm: 60, layers: [] }}
        onChange={vi.fn()}
        onLayersChange={(next) => {
          latest = next;
        }}
        specSheet={specSheet}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Add Table/ }));
    const table = latest.find((l) => (l.type as string) === 'table');
    expect(table).toBeTruthy();
    const props = table!.props as unknown as { kind: string; rows: unknown[]; columns: unknown[]; cells: unknown[][] };
    expect(props.kind).toBe('table');
    expect(props.rows).toHaveLength(3);
    expect(props.columns).toHaveLength(2);
    expect(props.cells.map((r) => r.length)).toEqual([2, 2, 2]);
  });
});

describe('table context menu', () => {
  it('right-click on a table layer offers the row, column and merge actions', () => {
    const { container } = render(
      <TagCanvasEditor doc={{ width_mm: 80, height_mm: 60, layers: [tableLayer('tbl')] }} onChange={vi.fn()} />,
    );
    const stageHost = container.querySelector('[data-konva="stage"]')!.parentElement!.parentElement!;
    fireEvent.contextMenu(stageHost, { clientX: 10 * CANVAS_PX_PER_MM, clientY: 10 * CANVAS_PX_PER_MM });
    for (const name of [/Insert row below/, /Insert column right/, /Delete row/, /Delete column/, /Merge cells/]) {
      expect(screen.getByRole('menuitem', { name })).toBeInTheDocument();
    }
  });

  it('a non-table layer does not offer them', () => {
    const { container } = render(
      <TagCanvasEditor
        doc={{ width_mm: 80, height_mm: 60, layers: [{ ...tableLayer('x'), type: 'shape', props: defaultShapeProps() } as TagLayer] }}
        onChange={vi.fn()}
      />,
    );
    const stageHost = container.querySelector('[data-konva="stage"]')!.parentElement!.parentElement!;
    fireEvent.contextMenu(stageHost, { clientX: 10 * CANVAS_PX_PER_MM, clientY: 10 * CANVAS_PX_PER_MM });
    expect(screen.queryByRole('menuitem', { name: /Insert row below/ })).toBeNull();
  });
});

describe('Merge down', () => {
  it('merges the clicked cell with the one below; disabled on the last row', () => {
    let latest: TagLayer[] = [];
    const { container } = render(
      <TagCanvasEditor
        doc={{ width_mm: 80, height_mm: 60, layers: [tableLayer('tbl')] }}
        onChange={vi.fn()}
        onLayersChange={(next) => {
          latest = next;
        }}
      />,
    );
    const host = container.querySelector('[data-konva="stage"]')!.parentElement!.parentElement!;
    // (10, 7) mm is the first cell of the first row of the 6 mm rows at (5, 5).
    fireEvent.contextMenu(host, { clientX: 10 * CANVAS_PX_PER_MM, clientY: 7 * CANVAS_PX_PER_MM });
    const item = screen.getByRole('menuitem', { name: /Merge down/ });
    expect(item.getAttribute('aria-disabled')).not.toBe('true');
    fireEvent.click(item);
    const cells = (latest.find((l) => (l.type as string) === 'table')!.props as unknown as { cells: { rowSpan?: number }[][] }).cells;
    expect(cells[0][0].rowSpan).toBe(2);
  });

  it('is disabled on the last row', () => {
    const { container } = render(
      <TagCanvasEditor doc={{ width_mm: 80, height_mm: 60, layers: [tableLayer('tbl')] }} onChange={vi.fn()} />,
    );
    const host = container.querySelector('[data-konva="stage"]')!.parentElement!.parentElement!;
    // Row 3 of 3 spans y 17..23 mm.
    fireEvent.contextMenu(host, { clientX: 10 * CANVAS_PX_PER_MM, clientY: 20 * CANVAS_PX_PER_MM });
    const item = screen.getByRole('menuitem', { name: /Merge down/ });
    expect(item.getAttribute('aria-disabled') === 'true' || item.hasAttribute('data-disabled')).toBe(true);
  });
});
