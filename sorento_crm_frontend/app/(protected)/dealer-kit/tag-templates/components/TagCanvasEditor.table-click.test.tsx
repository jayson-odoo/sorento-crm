/**
 * SPEC-SHEET-DESIGNER-PARITY B4: a left-click on a table cell selects the table and makes that cell
 * the Inspector's current cell. Written test-FIRST.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

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
  }: {
    layer: { id: string };
    onSelect?: (id: string, additive: boolean) => void;
  }) => <button data-testid={`layer-${layer.id}`} onClick={() => onSelect?.(layer.id, false)} />,
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

describe('clicking a table cell', () => {
  it('selects the table and drives the Inspector cell pickers', () => {
    render(<TagCanvasEditor doc={{ width_mm: 80, height_mm: 60, layers: [tableLayer('tbl')] }} onChange={vi.fn()} />);
    // Layer at (5, 5): columns 30 mm, rows 6 mm. (50, 14) mm is row 2, column 2 (1-based).
    pointer.x = 50 * CANVAS_PX_PER_MM;
    pointer.y = 14 * CANVAS_PX_PER_MM;
    fireEvent.click(screen.getByTestId('layer-tbl'));
    expect((screen.getByLabelText('Cell row') as HTMLInputElement).value).toBe('2');
    expect((screen.getByLabelText('Cell column') as HTMLInputElement).value).toBe('2');

    pointer.x = 10 * CANVAS_PX_PER_MM;
    pointer.y = 7 * CANVAS_PX_PER_MM;
    fireEvent.click(screen.getByTestId('layer-tbl'));
    expect((screen.getByLabelText('Cell row') as HTMLInputElement).value).toBe('1');
    expect((screen.getByLabelText('Cell column') as HTMLInputElement).value).toBe('1');
  });
});
