/**
 * SPEC-SHEET-PARITY-B2 v3 fix round, on the shared designer (`TagCanvasEditor`). Written test-FIRST.
 *
 * - B2 (AC-C3.1): the picked cell of the selected table is outlined (`table-cell-outline`, carrying
 *   the cell's row / col), not while typing in it.
 * - B3: a picked cell that no longer exists (Delete row, Undo of an added row) resolves to a cell
 *   that does: typing opens the editor on it, and the keyboard is never left dead.
 * - N6 (AC-C3.2): typing "{" on a picked cell opens the field picker; the field goes after its text.
 * - N5: the bottom edge strip leaves the Transformer's corner and centre handles free.
 * - F1 (template designer half): + Row and Header row from the toolbar are one Undo step each.
 */
import '@/test-utils/prosemirrorGeometry';
import * as React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
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
  KonvaTagLayer: ({
    layer,
    onSelect,
    onDoubleClick,
  }: {
    layer: { id: string };
    onSelect?: (id: string, additive: boolean) => void;
    onDoubleClick?: (id: string) => void;
  }) => (
    <div
      data-testid={`layer-${layer.id}`}
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


type Cells = { text: string; rowSpan?: number; colSpan?: number }[][];
type TableShape = { rows: { height_mm: number }[]; columns: { width_mm: number }[]; cells: Cells; headerRow?: boolean };

/** 3 rows x 2 columns at (5, 5): columns 30 mm, rows 6 mm, short 8 pt text (no row grows). */
function tableLayer(): TagLayer {
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
      fontSize: 8,
      color: '#000000',
      align: 'left',
      verticalAlign: 'middle',
    },
  } as unknown as TagLayer;
}

const tableOf = (layers: TagLayer[]) => layers.find((l) => l.id === 'tbl')?.props as unknown as TableShape;

function renderDesigner() {
  const latest: { layers: TagLayer[] } = { layers: [tableLayer()] };
  const view = render(
    <TagCanvasEditor
      doc={{ width_mm: 80, height_mm: 60, layers: [tableLayer()] }}
      onChange={vi.fn()}
      onLayersChange={(next) => {
        latest.layers = next;
      }}
    />,
  );
  return { ...view, latest };
}

function pointAt(row: number, col: number) {
  pointer.x = (5 + col * 30 + 10) * CANVAS_PX_PER_MM;
  pointer.y = (5 + row * 6 + 3) * CANVAS_PX_PER_MM;
}

function pick(row: number, col: number) {
  pointAt(row, col);
  fireEvent.click(screen.getByTestId('layer-tbl'));
}

function rightClick(container: HTMLElement, row: number, col: number) {
  pointAt(row, col);
  const host = container.querySelector('[data-konva="stage"]')!.parentElement!.parentElement!;
  fireEvent.contextMenu(host, { clientX: pointer.x, clientY: pointer.y });
}

const outline = () => screen.queryByTestId('table-cell-outline');

async function cellEditor() {
  const host = await screen.findByTestId('inline-rich-editor');
  return waitFor(() => {
    const el = host.querySelector<HTMLElement>('.ProseMirror');
    expect(el).not.toBeNull();
    return el!;
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('the picked cell is outlined (B2, AC-C3.1)', () => {
  it('no outline until a cell of the selected table is picked; then on that cell', () => {
    renderDesigner();
    expect(outline()).toBeNull();
    pick(1, 1);
    expect(outline()).toHaveAttribute('data-row', '1');
    expect(outline()).toHaveAttribute('data-col', '1');
    pick(0, 0);
    expect(outline()).toHaveAttribute('data-row', '0');
    expect(outline()).toHaveAttribute('data-col', '0');
  });

  it('no outline while the cell is being typed in', async () => {
    renderDesigner();
    pick(2, 1);
    fireEvent.doubleClick(screen.getByTestId('layer-tbl'));
    await cellEditor();
    expect(outline()).toBeNull();
  });
});

describe('a picked cell that is gone (B3)', () => {
  it('after Delete row of the picked row, typing opens the editor on a cell that exists and keys still work', async () => {
    const { container, latest } = renderDesigner();
    pick(2, 1);
    rightClick(container, 2, 1);
    fireEvent.click(screen.getByRole('menuitem', { name: /^Delete row/ }));
    expect(tableOf(latest.layers).rows).toHaveLength(2);
    expect(outline()).toHaveAttribute('data-row', '1');
    fireEvent.keyDown(window, { key: 'x' });
    const dom = await cellEditor();
    fireEvent.keyDown(dom, { key: 'Escape', bubbles: true });
    await waitFor(() => expect(screen.queryByTestId('inline-rich-editor')).toBeNull());
    fireEvent.keyDown(window, { key: 'Delete' });
    expect(latest.layers.find((l) => l.id === 'tbl')).toBeUndefined();
  });

  it('after Undo takes away the picked row, typing goes into the last row that is left', async () => {
    const { container, latest } = renderDesigner();
    rightClick(container, 2, 0);
    fireEvent.click(screen.getByRole('menuitem', { name: /^Insert row below/ }));
    pick(3, 0);
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(tableOf(latest.layers).rows).toHaveLength(3);
    fireEvent.keyDown(window, { key: 'x' });
    const dom = await cellEditor();
    fireEvent.keyDown(dom, { key: 'Enter', bubbles: true });
    await waitFor(() => expect(screen.queryByTestId('inline-rich-editor')).toBeNull());
    expect(tableOf(latest.layers).cells[2][0].text).toBe('Ex');
  });
});

describe('typing { on a picked cell (N6, AC-C3.2)', () => {
  it('opens the field picker, and the field goes after the cell text', async () => {
    const { latest } = renderDesigner();
    pick(0, 0);
    fireEvent.keyDown(window, { key: '{' });
    const dialog = await screen.findByRole('dialog', { name: 'Insert field' });
    fireEvent.change(within(dialog).getByPlaceholderText('Search fields...'), { target: { value: 'product.code' } });
    fireEvent.click(within(dialog).getByTitle('{{product.code}}'));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Insert field' })).toBeNull());
    expect(tableOf(latest.layers).cells[0][0].text).toBe('A{{product.code}}');
  });
});

describe('the bottom edge strip leaves the resize handles free (N5)', () => {
  it('is inset from both corners, unlike an inner row edge', () => {
    renderDesigner();
    pick(0, 0);
    const inner = screen.getByTestId('table-row-edge-0');
    const bottom = screen.getByTestId('table-row-edge-2');
    expect(parseFloat(bottom.style.left)).toBeGreaterThan(parseFloat(inner.style.left));
    expect(parseFloat(bottom.style.width)).toBeLessThan(parseFloat(inner.style.width));
  });
});

describe('table toolbar actions are one Undo step each (F1, template designer)', () => {
  it('+ Row then Undo', () => {
    const { latest } = renderDesigner();
    pick(0, 0);
    fireEvent.click(screen.getByRole('button', { name: /(\+ ?|add )row/i }));
    expect(tableOf(latest.layers).rows).toHaveLength(4);
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(tableOf(latest.layers).rows).toHaveLength(3);
    fireEvent.click(screen.getByRole('button', { name: 'Redo' }));
    expect(tableOf(latest.layers).rows).toHaveLength(4);
  });

  it('Header row then Undo', () => {
    const { latest } = renderDesigner();
    pick(0, 0);
    fireEvent.click(screen.getByRole('button', { name: /^Header row$/ }));
    expect(tableOf(latest.layers).headerRow).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(tableOf(latest.layers).headerRow).toBeFalsy();
  });
});

describe('a renamed font family follows on a spec sheet page (review S2)', () => {
  it('the embedded controller renames the family on the page layers, as the designer does on its document', () => {
    const latest: { layers: TagLayer[] } = { layers: [] };
    const controllerRef: { current: import('./TagCanvasEditor').EmbeddedController | null } = { current: null };
    const text = {
      ...tableLayer(),
      id: 'title',
      type: 'text',
      props: {
        kind: 'text',
        text: 'Title',
        fontFamily: 'Sorento Display',
        fontSize: 12,
        fontWeight: 400,
        color: '#000000',
        align: 'left',
        lineHeight: 1.2,
        letterSpacing: 0,
      },
    } as unknown as TagLayer;
    render(
      <TagCanvasEditor
        doc={{ width_mm: 100, height_mm: 60, layers: [text] }}
        onChange={vi.fn()}
        docId="sheet:k1"
        specSheet
        embedded={{ pxPerMm: 2, selectedLayerId: null, onSelect: () => undefined, controllerRef, active: true }}
        onLayersChange={(next) => {
          latest.layers = next;
        }}
      />,
    );
    act(() => controllerRef.current?.renameFontFamily?.('Sorento Display', 'Sorento Display Pro'));
    expect((latest.layers[0].props as { fontFamily: string }).fontFamily).toBe('Sorento Display Pro');
  });
});
