/**
 * PRICETAG-HEADER-DRAG round 2, review B2 / S1 / S2: with the header selected the editor's ONE
 * Transformer lets go of the box (its header has the handles); the first arrow press moves the header
 * from where its TEXT draws; and a header that stops existing (text cleared) ends the header
 * selection, so the box gets its handles and keys back.
 */
import { accessoryChrome } from '@/lib/dealer-kit/accessory-box';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultAccessoriesProps } from '@/lib/dealer-kit/tag-template-types';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

// A Stage and a Transformer with refs, so the editor's ONE Transformer really receives its nodes.
const transformerNodes = vi.fn();
vi.mock('react-konva', async () => {
  const React = await import('react');
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  const Stage = React.forwardRef(function Stage({ children }: { children?: React.ReactNode }, ref) {
    React.useImperativeHandle(ref, () => ({
      findOne: (selector: string) => ({ selector }),
      container: () => document.createElement('div'),
      getPointerPosition: () => null,
      batchDraw: () => {},
    }));
    return <div data-konva="stage">{children}</div>;
  });
  const Transformer = React.forwardRef(function Transformer(_props: Record<string, unknown>, ref) {
    React.useImperativeHandle(ref, () => ({
      nodes: (n?: unknown[]) => (n === undefined ? [] : transformerNodes(n)),
      getLayer: () => null,
      forceUpdate: () => {},
    }));
    return <div data-konva="transformer" />;
  });
  return {
    Stage,
    Layer: passthrough('layer'),
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Circle: passthrough('circle'),
    Line: passthrough('line'),
    Transformer,
  };
});

vi.mock('./KonvaTagLayer', () => ({
  KonvaTagLayer: ({
    layer,
    display,
    onSelect,
    onDragStart,
    onDragEnd,
    onDoubleClick,
  }: {
    layer: TagLayer;
    display?: { accessoryHeaderHidden?: boolean };
    onSelect?: (id: string, additive: boolean) => void;
    onDragStart?: (id: string) => void;
    onDragEnd?: (id: string) => void;
    onDoubleClick?: (id: string) => void;
  }) => (
    <div
      data-testid={`layer-${layer.id}`}
      data-header-hidden={display?.accessoryHeaderHidden ? 'yes' : ''}
      onMouseDown={() => onDragStart?.(layer.id)}
      onMouseUp={() => onDragEnd?.(layer.id)}
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

vi.mock('../../services/accessoryTemplateService', () => ({
  listAccessoryTemplates: vi.fn(async () => []),
  getAccessoryTemplate: vi.fn(async () => null),
  createAccessoryTemplate: vi.fn(),
  updateAccessoryTemplate: vi.fn(),
  getAccessoryTemplateUsage: vi.fn(async () => ({ templates: [] })),
}));

const TEMPLATES = [
  { id: 'p1', name: 'FREE vertical', design: {}, used_in: 2, created_by_name: null, created_at: '', updated_at: '' },
];
const hookStub = () => ({ data: undefined, isLoading: false, mutate: vi.fn(), mutateAsync: vi.fn(), run: vi.fn() });
vi.mock('../../accessory-templates/hooks/useAccessoryTemplates', () => ({
  // One saved template, so a linked box (presetId p1) can show its "changes here update" strip.
  useAccessoryTemplatesQuery: () => ({ ...hookStub(), data: TEMPLATES }),
  useAccessoryTemplateQuery: hookStub,
  useAccessoryTemplateUsage: hookStub,
  useCreateAccessoryTemplate: hookStub,
  useUpdateAccessoryTemplate: hookStub,
  useDeleteAccessoryTemplate: hookStub,
}));

vi.mock('./HeaderDragOverlay', () => ({
  HeaderDragOverlay: ({
    onMove,
    onDragState,
    onSelect,
    onResize,
    selected,
  }: {
    onMove: (p: { x_mm: number; y_mm: number }) => void;
    onDragState: (dragging: boolean) => void;
    onSelect: () => void;
    onResize: (r: { x_mm: number; y_mm: number; width_mm: number; height_mm: number }) => void;
    selected: boolean;
  }) => (
    <>
      <button type="button" data-testid="header-select" data-selected={selected ? 'yes' : ''} onClick={onSelect} />
      <button
        type="button"
        data-testid="header-resize"
        onClick={() => onResize({ x_mm: 2, y_mm: 3, width_mm: 22, height_mm: 9 })}
      />
      <button type="button" data-testid="header-handle" onClick={() => onMove({ x_mm: 4, y_mm: 30 })} />
      <button type="button" data-testid="header-grab" onClick={() => onDragState(true)} />
      <button type="button" data-testid="header-release" onClick={() => onDragState(false)} />
    </>
  ),
}));

import { TagCanvasEditor, transformerTargets } from './TagCanvasEditor';

function accessoriesLayer(id: string, props: Record<string, unknown> = {}): TagLayer {
  return {
    id,
    type: 'accessories',
    x_mm: 5,
    y_mm: 5,
    width_mm: 60,
    height_mm: 80,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultAccessoriesProps(), ...props },
  } as TagLayer;
}

function docWith(...layers: TagLayer[]): TagTemplateDoc {
  return { width_mm: 148, height_mm: 105, layers };
}

function mount(layer: TagLayer, mode?: 'live' | 'detach', patchesRef?: { current: unknown }) {
  const state = { layers: [] as TagLayer[] };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <TagCanvasEditor
        doc={docWith(layer)}
        onChange={vi.fn()}
        linkedAccessoryBoxes={mode}
        layerPatchesRef={patchesRef as never}
        onLayersChange={(layers) => {
          state.layers = layers;
        }}
      />
    </QueryClientProvider>,
  );
  return state;
}

const propsOf = (state: { layers: TagLayer[] }) =>
  state.layers[0].props as unknown as { headerPos?: unknown; presetId?: string | null };

const lastNodes = () => (transformerNodes.mock.calls.at(-1)?.[0] ?? []) as { selector: string }[];

describe('the Transformer, the header and the box', () => {
  it('transformerTargets drops the box whose header is selected, and locked / hidden layers', () => {
    const a = accessoriesLayer('a');
    const b = { ...accessoriesLayer('b'), locked: true };
    const c = { ...accessoriesLayer('c'), visible: false };
    expect(transformerTargets([a, b, c], null).map((l) => l.id)).toEqual(['a']);
    expect(transformerTargets([a], 'a')).toEqual([]);
  });

  it('header selected: the box is not handed to the Transformer; Escape gives it back', () => {
    mount(accessoriesLayer('acc1'));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    expect(lastNodes().map((n) => n.selector)).toEqual(['#acc1']);
    fireEvent.click(screen.getByTestId('header-select'));
    expect(lastNodes()).toEqual([]);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(lastNodes().map((n) => n.selector)).toEqual(['#acc1']);
  });

  it('the first arrow press moves an inside-frame header from where its text draws', () => {
    const layer = accessoriesLayer('acc1', { headerOnBorder: false, headerText: 'FREE' });
    const state = mount(layer);
    fireEvent.click(screen.getByTestId('layer-acc1'));
    fireEvent.click(screen.getByTestId('header-select'));
    fireEvent.keyDown(window, { key: 'ArrowRight' });
    const pos = (state.layers[0].props as unknown as { headerPos: { x_mm: number; y_mm: number } }).headerPos;
    // The text's own span, not the full-width band (sample cards: the box closes up, width stays).
    const text = accessoryChrome(layer.props as never, layer.width_mm, 40).header!.text;
    expect(pos.x_mm).toBeGreaterThan(text.x_mm);
    expect(pos.x_mm - text.x_mm).toBeLessThan(2);
    expect(pos.y_mm).toBeCloseTo(text.y_mm, 6);
  });

  it('clearing the header text ends the header selection: box Inspector and box handles again', () => {
    mount(accessoriesLayer('acc1'));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    fireEvent.click(screen.getByTestId('header-select'));
    expect(screen.getByText('Background')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Header text'), { target: { value: '' } });
    expect(screen.queryByText('Background')).toBeNull();
    expect(lastNodes().map((n) => n.selector)).toEqual(['#acc1']);
  });
});
