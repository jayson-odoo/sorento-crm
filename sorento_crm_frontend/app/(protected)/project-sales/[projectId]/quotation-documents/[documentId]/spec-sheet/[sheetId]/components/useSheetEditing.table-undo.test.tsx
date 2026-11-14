/**
 * SPEC-SHEET-PARITY-B2 v3 fix round, browser F1: on the SPEC SHEET page every table edit (row edge
 * drag, + Row, Header row) is one step of the page's own undo history (`useSheetEditing`), so Undo
 * puts it back, Redo does it again, and Ctrl+Z works the same. The real designer canvas (embedded)
 * and the real page history are wired the way `ReaderPage` wires them. Written test-FIRST.
 */
import * as React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { TableLayerProps, TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';

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

vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/KonvaTagLayer', () => ({
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

vi.mock('@/app/(protected)/dealer-kit/services/assetService', () => ({
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
}));

vi.mock('@/app/(protected)/dealer-kit/services/tagDataService', () => ({
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

vi.mock('@/app/(protected)/project-sales/_shared/hooks/useSpecSheet', () => ({
  useSpecSheetMutations: () => ({ autosavePage: { mutateAsync: vi.fn(async () => undefined) } }),
}));

import {
  TagCanvasEditor,
  type EmbeddedController,
  type EmbeddedMode,
} from '@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor';
import { insertRow } from '@/lib/dealer-kit/table-layout';
import { useSheetEditing } from './useSheetEditing';


type TableShape = { rows: { height_mm: number }[]; headerRow?: boolean };

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

const latest: { layers: TagLayer[] } = { layers: [] };
const tableNow = () => latest.layers.find((l) => l.id === 'tbl')!.props as unknown as TableShape & TableLayerProps;

function Page() {
  const editing = useSheetEditing('p1', 'd1', 'sheet-1');
  const [selected, setSelected] = React.useState<string | null>('tbl');
  const controllerRef = React.useRef<EmbeddedController | null>(null);
  const doc = React.useMemo<TagTemplateDoc>(() => ({ width_mm: 100, height_mm: 60, layers: [tableLayer()] }), []);
  const external = editing.externalOf('k1');
  const embedded = React.useMemo<EmbeddedMode>(
    () => ({
      pxPerMm: 2,
      selectedLayerId: selected,
      onSelect: setSelected,
      controllerRef,
      active: true,
      readOnly: false,
      layers: external,
      onHistory: (step) => (step < 0 ? editing.undo('k1') : editing.redo('k1')),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selected, external],
  );
  const onLayersChange = React.useCallback(
    (layers: TagLayer[]) => {
      latest.layers = layers;
      editing.report('k1', doc.layers, layers);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [doc],
  );
  return (
    <>
      <button type="button" onClick={() => editing.undo('k1')}>
        page undo
      </button>
      <button type="button" onClick={() => editing.redo('k1')}>
        page redo
      </button>
      <span data-testid="history">{`${editing.canUndo('k1')}:${editing.canRedo('k1')}`}</span>
      <button type="button" onClick={() => controllerRef.current?.updateLayerProps('tbl', { headerRow: true })}>
        header on
      </button>
      <button type="button" onClick={() => controllerRef.current?.updateLayerProps('tbl', insertRow(tableNow(), 3))}>
        add row
      </button>
      <TagCanvasEditor
        doc={doc}
        onChange={vi.fn()}
        docId="sheet:k1"
        specSheet
        embedded={embedded}
        onLayersChange={onLayersChange}
      />
    </>
  );
}

const history = () => screen.getByTestId('history').textContent;

function dragRowEdge(index: number, dy_mm: number) {
  const strip = screen.getByTestId(`table-row-edge-${index}`);
  const start = { clientX: 100, clientY: 100, pointerId: 1, button: 0 };
  const end = { ...start, clientY: 100 + dy_mm * 2 };
  fireEvent.pointerDown(strip, start);
  fireEvent.pointerMove(strip, end);
  fireEvent.pointerUp(strip, end);
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'], shouldAdvanceTime: true });
  latest.layers = [];
});

afterEach(() => {
  vi.useRealTimers();
});

describe('table edits are page undo steps on the spec sheet (browser F1)', () => {
  it('a row edge drag: Undo puts the row back, Redo does it again', () => {
    render(<Page />);
    dragRowEdge(0, 4);
    expect(tableNow().rows[0].height_mm).toBe(10);
    expect(history()).toBe('true:false');
    fireEvent.click(screen.getByRole('button', { name: 'page undo' }));
    expect(tableNow().rows[0].height_mm).toBe(6);
    expect(history()).toBe('false:true');
    fireEvent.click(screen.getByRole('button', { name: 'page redo' }));
    expect(tableNow().rows[0].height_mm).toBe(10);
  });

  it('+ Row: Undo takes the row away again', () => {
    render(<Page />);
    fireEvent.click(screen.getByRole('button', { name: 'add row' }));
    expect(tableNow().rows).toHaveLength(4);
    fireEvent.click(screen.getByRole('button', { name: 'page undo' }));
    expect(tableNow().rows).toHaveLength(3);
    expect(history()).toBe('false:true');
  });

  it('Header row: Ctrl+Z on the page turns it off again', () => {
    render(<Page />);
    fireEvent.click(screen.getByRole('button', { name: 'header on' }));
    expect(tableNow().headerRow).toBe(true);
    act(() => {
      fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
    });
    expect(tableNow().headerRow).toBeFalsy();
    expect(history()).toBe('false:true');
  });

  it('two edits are two steps', () => {
    render(<Page />);
    dragRowEdge(0, 4);
    fireEvent.click(screen.getByRole('button', { name: 'header on' }));
    fireEvent.click(screen.getByRole('button', { name: 'page undo' }));
    expect(tableNow().headerRow).toBeFalsy();
    expect(tableNow().rows[0].height_mm).toBe(10);
    fireEvent.click(screen.getByRole('button', { name: 'page undo' }));
    expect(tableNow().rows[0].height_mm).toBe(6);
  });
});
