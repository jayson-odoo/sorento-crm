/**
 * SPEC-SHEET-PARITY-B2 v3 (browser follow-up, 375 px): the canvas right-click menu stays inside a
 * phone screen. Radix places a context menu to the right of the pointer, or flips it to the left,
 * and never shifts it sideways, so a 224 px menu opened mid-screen at 375 px fits on neither side
 * and runs off the edge (seen: x 177..401). Below `sm` the menu is at most half the screen wide
 * (less the 8 px collision padding), so one side always fits, and the keyboard shortcuts (no
 * keyboard on a phone) are left out; from `sm` up it sizes to its longest item, never wider than
 * the screen. jsdom does no layout, so this pins the classes that carry it. Written test-FIRST.
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

describe('the canvas right-click menu on a phone', () => {
  it('is at most half the screen wide below sm, without shortcuts; sized to its items from sm up', () => {
    const { container } = renderDesigner();
    rightClick(container, 0, 0);
    const panel = screen.getByRole('menu').firstElementChild as HTMLElement;
    const classes = panel.className.split(/\s+/);
    for (const cls of [
      'w-[calc(50vw-8px)]',
      'max-sm:[&_[data-slot=context-menu-shortcut]]:hidden',
      'sm:w-max',
      'sm:min-w-56',
      'sm:max-w-[calc(100vw-16px)]',
    ]) {
      expect(classes, cls).toContain(cls);
    }
    expect(screen.getByRole('menuitem', { name: /^Insert row below/ })).toBeInTheDocument();
  });
});
