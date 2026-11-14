/**
 * SPEC-SHEET-PARITY-B2 v3 editor, C3 (+ the table parts of C1.4 / C4.1): table cells are edited ON
 * THE PAGE, in the shared designer (`TagCanvasEditor`), template designer and spec sheet page alike.
 * Written test-FIRST.
 *
 * - AC-C3.1: double-clicking a cell opens the in-place rich editor (`inline-rich-editor`, the one
 *   text layers use) over that cell, seeded with the cell text, `{{fields}}` as chips.
 * - AC-C3.2: typing `{` in the cell editor (keydown, key "{") opens the "Insert field" dialog; the
 *   picked field lands AT THE CURSOR. Right-click > Insert field on a cell with text appends after
 *   it (never at the start).
 * - AC-C3.3: Enter saves the cell text, Escape cancels; the edit is one Undo step.
 * - AC-C3.5: right-click on a cell lists Insert field, Insert row above / below, Insert column
 *   left / right, Delete row / column, Merge right, Merge down, Unmerge cells, Header row (a
 *   checkbox item, checked when on).
 * - AC-C3.7: the same in-place editor opens on an embedded (spec sheet) page.
 * - AC-C1.4 / AC-C4.1: with a table selected the toolbar shows the table actions, Header row
 *   among them, and it toggles `props.headerRow`.
 */
import '@/test-utils/prosemirrorGeometry';
import * as React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

import { TagCanvasEditor, type EmbeddedMode } from './TagCanvasEditor';

// ---- fixtures ---------------------------------------------------------------------------------

type Cells = { text: string; rowSpan?: number; colSpan?: number }[][];
type TableShape = { rows: { height_mm: number }[]; columns: { width_mm: number }[]; cells: Cells; headerRow?: boolean };

/** 3 rows x 2 columns at (5, 5): columns 30 mm, rows 6 mm. */
function tableLayer(texts: string[][], extra: Record<string, unknown> = {}): TagLayer {
  const side = { color: '#000000', width_mm: 0.2 };
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
      fontSize: 10,
      color: '#000000',
      align: 'left',
      verticalAlign: 'middle',
      ...extra,
    },
  } as unknown as TagLayer;
}

const TEXTS = [
  ['REF', '{{doc.ref}}'],
  ['Code', 'Ref {{product.code}}'],
  ['Size', 'AB'],
];

/** Put the pointer over cell (row, col) of the fixture table (1-based maths kept out of the tests). */
function pointAt(row: number, col: number) {
  pointer.x = (5 + col * 30 + 10) * CANVAS_PX_PER_MM;
  pointer.y = (5 + row * 6 + 3) * CANVAS_PX_PER_MM;
}

function renderDesigner(layer: TagLayer = tableLayer(TEXTS)) {
  const latest: { layers: TagLayer[] } = { layers: [layer] };
  const view = render(
    <TagCanvasEditor
      doc={{ width_mm: 80, height_mm: 60, layers: [layer] }}
      onChange={vi.fn()}
      onLayersChange={(next) => {
        latest.layers = next;
      }}
    />,
  );
  return { ...view, latest };
}

const tableOf = (layers: TagLayer[]) =>
  layers.find((l) => (l.type as string) === 'table')!.props as unknown as TableShape;

async function cellEditor(): Promise<{ dom: HTMLElement; editor: import('@tiptap/react').Editor }> {
  const host = await screen.findByTestId('inline-rich-editor');
  const dom = await waitFor(() => {
    const el = host.querySelector<HTMLElement>('.ProseMirror');
    expect(el).not.toBeNull();
    return el!;
  });
  return { dom, editor: (dom as unknown as { editor: import('@tiptap/react').Editor }).editor };
}

function openCell(row: number, col: number) {
  pointAt(row, col);
  fireEvent.click(screen.getByTestId('layer-tbl'));
  fireEvent.doubleClick(screen.getByTestId('layer-tbl'));
}

/** Pick a field in the open Insert field dialog by its token, then confirm if the dialog asks. */
function pickField(token: string, search: string) {
  const dialog = screen.getByRole('dialog', { name: 'Insert field' });
  fireEvent.change(within(dialog).getByPlaceholderText('Search fields...'), { target: { value: search } });
  fireEvent.click(within(dialog).getByTitle(token));
  const confirm = screen
    .queryAllByRole('button', { name: /^(Insert|Done)$/ })
    .find((b) => dialog.contains(b));
  if (confirm && document.body.contains(dialog)) fireEvent.click(confirm);
}

/** Enter on the cell editor if it is still open, then wait for it to close. */
async function saveCellIfOpen() {
  const host = screen.queryByTestId('inline-rich-editor');
  const dom = host?.querySelector<HTMLElement>('.ProseMirror');
  if (dom) fireEvent.keyDown(dom, { key: 'Enter', bubbles: true });
  await waitFor(() => expect(screen.queryByTestId('inline-rich-editor')).toBeNull());
}

function rightClickCell(container: HTMLElement, row: number, col: number) {
  pointAt(row, col);
  const host = container.querySelector('[data-konva="stage"]')!.parentElement!.parentElement!;
  fireEvent.contextMenu(host, { clientX: pointer.x, clientY: pointer.y });
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---- AC-C3.1 / C3.3 -----------------------------------------------------------------------------

describe('editing a cell in place (AC-C3.1, AC-C3.3)', () => {
  it('double-click opens the rich in-place editor on THAT cell, fields as chips', async () => {
    renderDesigner();
    openCell(1, 1);
    const { dom } = await cellEditor();
    expect(dom.textContent).toContain('Ref');
    expect(dom.querySelector('[data-merge-field="product.code"]')).not.toBeNull();
    expect(dom.textContent).not.toContain('{{product.code}}');
  });

  it('Enter saves the typed text into that cell only', async () => {
    const { latest } = renderDesigner();
    openCell(2, 1);
    const { dom, editor } = await cellEditor();
    editor.chain().focus('end').insertContent('C').run();
    fireEvent.keyDown(dom, { key: 'Enter', bubbles: true });
    await waitFor(() => expect(screen.queryByTestId('inline-rich-editor')).toBeNull());
    const cells = tableOf(latest.layers).cells;
    expect(cells[2][1].text).toBe('ABC');
    expect(cells[2][0].text).toBe('Size');
    expect(cells[1][1].text).toBe('Ref {{product.code}}');
  });

  it('Escape cancels: the cell keeps its text', async () => {
    const { latest } = renderDesigner();
    openCell(2, 1);
    const { dom, editor } = await cellEditor();
    editor.chain().focus('end').insertContent('C').run();
    fireEvent.keyDown(dom, { key: 'Escape', bubbles: true });
    await waitFor(() => expect(screen.queryByTestId('inline-rich-editor')).toBeNull());
    expect(tableOf(latest.layers).cells[2][1].text).toBe('AB');
  });

  it('a saved cell edit is one Undo step', async () => {
    const { latest } = renderDesigner();
    openCell(2, 1);
    const { dom, editor } = await cellEditor();
    editor.chain().focus('end').insertContent('C').run();
    fireEvent.keyDown(dom, { key: 'Enter', bubbles: true });
    await waitFor(() => expect(tableOf(latest.layers).cells[2][1].text).toBe('ABC'));
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(tableOf(latest.layers).cells[2][1].text).toBe('AB');
  });
});

// ---- AC-C3.2 ------------------------------------------------------------------------------------

describe('Insert field lands at the cursor (AC-C3.2)', () => {
  it('typing { in the cell editor opens the field picker; the field goes in at the caret', async () => {
    const { latest } = renderDesigner();
    openCell(2, 1);
    const { dom, editor } = await cellEditor();
    // Caret between "A" and "B" (position 2 inside the first paragraph).
    editor.chain().focus().setTextSelection(2).run();
    fireEvent.keyDown(dom, { key: '{', bubbles: true });

    expect(await screen.findByRole('dialog', { name: 'Insert field' })).toBeInTheDocument();
    pickField('{{product.code}}', 'product.code');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Insert field' })).toBeNull());
    await saveCellIfOpen();

    expect(tableOf(latest.layers).cells[2][1].text).toBe('A{{product.code}}B');
  });

  it('right-click > Insert field on a cell with text puts the field after it, never at the start', async () => {
    const { container, latest } = renderDesigner();
    rightClickCell(container, 0, 0);
    fireEvent.click(screen.getByRole('menuitem', { name: /Insert field/ }));
    expect(await screen.findByRole('dialog', { name: 'Insert field' })).toBeInTheDocument();
    pickField('{{product.code}}', 'product.code');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Insert field' })).toBeNull());
    await saveCellIfOpen();

    const text = tableOf(latest.layers).cells[0][0].text;
    expect(text.startsWith('REF')).toBe(true);
    expect(text).toContain('{{product.code}}');
  });
});

// ---- AC-C3.5 ------------------------------------------------------------------------------------

describe('right-click on a cell (AC-C3.5)', () => {
  const ITEMS = [
    /^Insert field/,
    /^Insert row above/,
    /^Insert row below/,
    /^Insert column left/,
    /^Insert column right/,
    /^Delete row/,
    /^Delete column/,
    /^Merge right/,
    /^Merge down/,
    /^Unmerge cells/,
  ];

  it('lists every table action, Header row as a checkbox item', () => {
    const { container } = renderDesigner();
    rightClickCell(container, 0, 0);
    for (const name of ITEMS) expect(screen.getByRole('menuitem', { name }), String(name)).toBeInTheDocument();
    expect(screen.getByRole('menuitemcheckbox', { name: /Header row/ })).toHaveAttribute('aria-checked', 'false');
  });

  it('Header row is checked on a table that has it, and choosing it turns it off', () => {
    const { container, latest } = renderDesigner(tableLayer(TEXTS, { headerRow: true }));
    rightClickCell(container, 1, 0);
    const item = screen.getByRole('menuitemcheckbox', { name: /Header row/ });
    expect(item).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(item);
    expect(tableOf(latest.layers).headerRow).toBeFalsy();
  });

  it('Header row on a plain table turns it on', () => {
    const { container, latest } = renderDesigner();
    rightClickCell(container, 1, 0);
    fireEvent.click(screen.getByRole('menuitemcheckbox', { name: /Header row/ }));
    expect(tableOf(latest.layers).headerRow).toBe(true);
  });

  it('Insert row above puts a blank row at the clicked row', () => {
    const { container, latest } = renderDesigner();
    rightClickCell(container, 1, 0);
    fireEvent.click(screen.getByRole('menuitem', { name: /^Insert row above/ }));
    const cells = tableOf(latest.layers).cells;
    expect(cells.map((r) => r[0].text)).toEqual(['REF', '', 'Code', 'Size']);
  });

  it('Insert column left puts a blank column at the clicked column', () => {
    const { container, latest } = renderDesigner();
    rightClickCell(container, 0, 1);
    fireEvent.click(screen.getByRole('menuitem', { name: /^Insert column left/ }));
    const cells = tableOf(latest.layers).cells;
    expect(cells[0].map((c) => c.text)).toEqual(['REF', '', '{{doc.ref}}']);
  });

  it('Merge right joins the clicked cell with the one to its right', () => {
    const { container, latest } = renderDesigner();
    rightClickCell(container, 0, 0);
    fireEvent.click(screen.getByRole('menuitem', { name: /^Merge right/ }));
    expect(tableOf(latest.layers).cells[0][0].colSpan).toBe(2);
  });
});

// ---- AC-C1.4 / AC-C4.1: table actions in the toolbar row ---------------------------------------

describe('table selected: table actions in the toolbar (AC-C1.4, AC-C4.1)', () => {
  it('shows + Row, + Column, Merge, Header row and Insert field; Header row toggles headerRow', () => {
    const { latest } = renderDesigner();
    pointAt(0, 0);
    fireEvent.click(screen.getByTestId('layer-tbl'));
    const header = screen.getByRole('button', { name: /^Header row$/ });
    for (const name of [/(\+ ?|add )row/i, /(\+ ?|add )column/i, /^merge/i, /^insert field$/i]) {
      expect(screen.getAllByRole('button', { name }).length, String(name)).toBeGreaterThan(0);
    }
    expect(header).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(header);
    expect(tableOf(latest.layers).headerRow).toBe(true);
  });

  it('with nothing selected there are no table actions', () => {
    renderDesigner();
    expect(screen.queryByRole('button', { name: /^Header row$/ })).toBeNull();
  });
});

// ---- AC-C3.7: the same on a spec sheet page (embedded) -----------------------------------------

describe('spec sheet page (embedded): the same in-place cell editor (AC-C3.7)', () => {
  function Page({ latest }: { latest: { layers: TagLayer[] } }) {
    const [selected, setSelected] = React.useState<string | null>(null);
    const embedded: EmbeddedMode = {
      pxPerMm: 2,
      selectedLayerId: selected,
      onSelect: setSelected,
      controllerRef: { current: null },
      active: true,
      readOnly: false,
    };
    // One 1 x 1 table filling the page, so any pointer position is the one cell.
    const one = tableLayer([['Ref {{doc.ref}}']]);
    const layer = { ...one, x_mm: 0, y_mm: 0, width_mm: 100, height_mm: 60 } as TagLayer;
    (layer.props as unknown as TableShape).columns = [{ width_mm: 100 }];
    (layer.props as unknown as TableShape).rows = [{ height_mm: 60 }];
    return (
      <TagCanvasEditor
        doc={{ width_mm: 100, height_mm: 60, layers: [layer] } as TagTemplateDoc}
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

  it('double-click on a cell opens the rich editor and Enter saves it', async () => {
    const latest: { layers: TagLayer[] } = { layers: [] };
    render(<Page latest={latest} />);
    pointer.x = 20;
    pointer.y = 20;
    fireEvent.click(screen.getByTestId('layer-tbl'));
    fireEvent.doubleClick(screen.getByTestId('layer-tbl'));
    const { dom, editor } = await cellEditor();
    expect(dom.querySelector('[data-merge-field="doc.ref"]')).not.toBeNull();
    editor.chain().focus('end').insertContent('!').run();
    fireEvent.keyDown(dom, { key: 'Enter', bubbles: true });
    await waitFor(() => expect(screen.queryByTestId('inline-rich-editor')).toBeNull());
    expect(tableOf(latest.layers).cells[0][0].text).toBe('Ref {{doc.ref}}!');
  });
});
