/**
 * PRICETAG-HEADER-DRAG: the editor wires the header handle. It shows for the one selected, unlocked
 * accessories box; a drop stores `headerPos` on that box as one step and never moves the box. Owner Q5
 * (a): the spot is design, so the template editor keeps the link (the saved template follows) and the
 * request designer detaches first, as for any other design edit there.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultAccessoriesProps } from '@/lib/dealer-kit/tag-template-types';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    Stage: passthrough('stage'),
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

import { TagCanvasEditor } from './TagCanvasEditor';

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

describe('header drag in the Tag Template designer', () => {
  it('no handle until the box is selected', () => {
    mount(accessoriesLayer('acc1'));
    expect(screen.queryByTestId('header-handle')).toBeNull();
    fireEvent.click(screen.getByTestId('layer-acc1'));
    expect(screen.getByTestId('header-handle')).toBeInTheDocument();
  });

  it('a drop stores the header spot and leaves the box where it is; undo puts it back', () => {
    const state = mount(accessoriesLayer('acc1'));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    fireEvent.click(screen.getByTestId('header-handle'));
    expect(propsOf(state).headerPos).toEqual({ x_mm: 4, y_mm: 30 });
    expect(state.layers[0].x_mm).toBe(5);
    expect(state.layers[0].y_mm).toBe(5);
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
    expect(propsOf(state).headerPos ?? null).toBeNull();
  });

  it('the box hides its own header text only while the header is dragged', () => {
    mount(accessoriesLayer('acc1'));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    expect(screen.getByTestId('layer-acc1').getAttribute('data-header-hidden')).toBe('');
    fireEvent.click(screen.getByTestId('header-grab'));
    expect(screen.getByTestId('layer-acc1').getAttribute('data-header-hidden')).toBe('yes');
    fireEvent.click(screen.getByTestId('header-release'));
    expect(screen.getByTestId('layer-acc1').getAttribute('data-header-hidden')).toBe('');
  });

  it('the handle hides while the box itself is dragged, and comes back after', () => {
    mount(accessoriesLayer('acc1'));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    expect(screen.getByTestId('header-handle')).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByTestId('layer-acc1'));
    expect(screen.queryByTestId('header-handle')).toBeNull();
    fireEvent.mouseUp(screen.getByTestId('layer-acc1'));
    expect(screen.getByTestId('header-handle')).toBeInTheDocument();
  });

  it('a locked box has no handle', () => {
    mount({ ...accessoriesLayer('acc1'), locked: true });
    fireEvent.click(screen.getByTestId('layer-acc1'));
    expect(screen.queryByTestId('header-handle')).toBeNull();
  });

  it('a hidden header has no handle', () => {
    mount(accessoriesLayer('acc1', { showHeader: false }));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    expect(screen.queryByTestId('header-handle')).toBeNull();
  });

  it('template editor: a linked box keeps its link (the saved template follows, Q5 a)', () => {
    const state = mount(accessoriesLayer('acc1', { presetId: 'p1' }));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    fireEvent.click(screen.getByTestId('header-handle'));
    expect(propsOf(state).presetId).toBe('p1');
    expect(propsOf(state).headerPos).toEqual({ x_mm: 4, y_mm: 30 });
  });

  it('request designer: a linked box is detached by the move', () => {
    const state = mount(accessoriesLayer('acc1', { presetId: 'p1' }), 'detach');
    fireEvent.click(screen.getByTestId('layer-acc1'));
    fireEvent.click(screen.getByTestId('header-handle'));
    expect(propsOf(state).presetId ?? null).toBeNull();
    expect(propsOf(state).headerPos).toEqual({ x_mm: 4, y_mm: 30 });
  });

  it('clicking the header selects it: header Inspector, no box Transformer target, Escape back to the box', () => {
    mount(accessoriesLayer('acc1'));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    expect(screen.queryByText('Background')).toBeNull();
    fireEvent.click(screen.getByTestId('header-select'));
    expect(screen.getByTestId('header-select').getAttribute('data-selected')).toBe('yes');
    expect(screen.getByText('Background')).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByTestId('header-select').getAttribute('data-selected')).toBe('');
    expect(screen.queryByText('Background')).toBeNull();
  });

  it('Delete with the header selected never deletes the box', () => {
    const state = mount(accessoriesLayer('acc1'));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    fireEvent.click(screen.getByTestId('header-select'));
    fireEvent.keyDown(window, { key: 'Delete' });
    expect(state.layers).toHaveLength(1);
  });

  it('a resize stores position and size as one step; the box keeps its place', () => {
    const state = mount(accessoriesLayer('acc1'));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    fireEvent.click(screen.getByTestId('header-select'));
    fireEvent.click(screen.getByTestId('header-resize'));
    expect(propsOf(state).headerPos).toEqual({ x_mm: 2, y_mm: 3 });
    expect((state.layers[0].props as unknown as { headerSize?: unknown }).headerSize).toEqual({ width_mm: 22, height_mm: 9 });
    expect(state.layers[0].x_mm).toBe(5);
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
    expect(propsOf(state).headerPos ?? null).toBeNull();
  });

  it('a linked box shows the "changes here update" strip while its header is selected or dragged', () => {
    mount(accessoriesLayer('acc1', { presetId: 'p1' }));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    expect(screen.queryByText(/changes here update/)).toBeNull();
    fireEvent.click(screen.getByTestId('header-grab'));
    expect(screen.getByText(/changes here update/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('header-release'));
    fireEvent.click(screen.getByTestId('header-select'));
    expect(screen.getByText(/changes here update/)).toBeInTheDocument();
  });
});
