/**
 * SPEC-SHEET-DESIGNER-PARITY slice A2: clipboard parity in the spec sheet designer.
 *
 * The spec sheet reader embeds one `TagCanvasEditor` per page (`embedded` mode). Before this
 * lane both window listeners - the keydown shortcuts and the copy/cut/paste events - returned
 * early whenever the canvas was embedded, so Cmd/Ctrl+C / X / V / D did nothing on a spec sheet
 * page. Now the ONE page the host marks `active` answers them, exactly like the price tag
 * designer; every other page stays silent so a paste never lands on several pages at once.
 *
 * Also: the context menu's Paste reads the SYSTEM clipboard (a screenshot, copied words) when
 * the editor holds no copied layers, in both designers - it used to be disabled.
 */

import * as React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultShapeProps } from '@/lib/dealer-kit/tag-template-types';
import { setTagClipboard } from '@/lib/dealer-kit/tag-clipboard';
import { TAG_LAYERS_MIME } from '@/lib/dealer-kit/clipboard-paste';

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
  KonvaTagLayer: ({
    layer,
    onSelect,
  }: {
    layer: TagLayer;
    onSelect?: (id: string, additive: boolean) => void;
  }) => <div data-testid={`layer-${layer.id}`} onClick={() => onSelect?.(layer.id, false)} />,
}));

vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => ({ failed: [] })),
  ensureSeedFontsLoaded: vi.fn(async () => {}),
  TAG_FONT_STYLESHEET: '',
  SEED_FONT_FAMILIES: [],
}));

const uploadAsset = vi.fn();
vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
  uploadAsset: (...args: unknown[]) => uploadAsset(...args),
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

vi.mock('@/lib/toast', () => ({
  toast: Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    loading: vi.fn(() => 'toast-id'),
    dismiss: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  }),
}));

vi.mock('@/lib/dealer-kit/clipboard-paste', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/dealer-kit/clipboard-paste')>();
  return { ...actual, readImageSize: vi.fn(async () => ({ width: 200, height: 100 })) };
});

import { TagCanvasEditor, type EmbeddedMode } from './TagCanvasEditor';

function shape(id: string): TagLayer {
  return {
    id,
    type: 'shape',
    x_mm: 10,
    y_mm: 10,
    width_mm: 20,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: defaultShapeProps(),
  };
}

function docWith(...layers: TagLayer[]): TagTemplateDoc {
  return { width_mm: 100, height_mm: 60, layers };
}

function pasteEvent(opts: { types?: Record<string, string>; files?: File[] }) {
  const types = opts.types ?? {};
  const files = opts.files ?? [];
  const event = new Event('paste', { bubbles: true, cancelable: true });
  Object.defineProperty(event, 'clipboardData', {
    value: {
      types: [...Object.keys(types), ...(files.length ? ['Files'] : [])],
      getData: (type: string) => types[type] ?? '',
      files,
    },
  });
  act(() => {
    window.dispatchEvent(event);
  });
  return event;
}

const png = () => new File([new Uint8Array(16)], 'image.png', { type: 'image/png' });

/** Two pages side by side, like the reader: the host owns selection and which page is active. */
function TwoPages({
  state,
  active,
  readOnly = false,
}: {
  state: Record<string, TagLayer[]>;
  active: 'a' | 'b';
  readOnly?: boolean;
}) {
  const [selected, setSelected] = React.useState<{ page: string; id: string | null }>({
    page: active,
    id: null,
  });
  const page = (key: 'a' | 'b') => {
    const embedded: EmbeddedMode = {
      pxPerMm: 2,
      selectedLayerId: selected.page === key ? selected.id : null,
      onSelect: (id) => setSelected({ page: key, id }),
      controllerRef: { current: null },
      active: active === key,
      readOnly,
    };
    return (
      <div data-testid={`page-${key}`}>
        <TagCanvasEditor
          doc={docWith(shape(`${key}1`))}
          onChange={vi.fn()}
          docId={`sheet:${key}`}
          specSheet
          embedded={embedded}
          onLayersChange={(layers) => {
            state[key] = layers;
          }}
        />
      </div>
    );
  };
  return (
    <>
      {page('a')}
      {page('b')}
    </>
  );
}

beforeEach(() => {
  uploadAsset.mockReset();
  uploadAsset.mockResolvedValue({ id: 'asset-new', name: 'Pasted image' });
});

afterEach(() => {
  setTagClipboard(null);
});

describe('embedded canvas (spec sheet page) clipboard', () => {
  it('Ctrl+C then the paste event pastes onto the ACTIVE page only', () => {
    const state: Record<string, TagLayer[]> = {};
    render(<TwoPages state={state} active="a" />);
    fireEvent.click(screen.getByTestId('layer-a1'));
    fireEvent.keyDown(window, { key: 'c', ctrlKey: true });
    pasteEvent({ types: { [TAG_LAYERS_MIME]: 'sheet:a' } });
    expect(state.a).toHaveLength(2);
    expect(state.b).toHaveLength(1);
  });

  it('Cmd+D duplicates the selected layer on the active page', () => {
    const state: Record<string, TagLayer[]> = {};
    render(<TwoPages state={state} active="a" />);
    fireEvent.click(screen.getByTestId('layer-a1'));
    fireEvent.keyDown(window, { key: 'd', metaKey: true });
    expect(state.a).toHaveLength(2);
    expect(state.b).toHaveLength(1);
  });

  it('Ctrl+X cuts: the layer leaves the page and pastes back', () => {
    const state: Record<string, TagLayer[]> = {};
    render(<TwoPages state={state} active="a" />);
    fireEvent.click(screen.getByTestId('layer-a1'));
    fireEvent.keyDown(window, { key: 'x', ctrlKey: true });
    expect(state.a).toHaveLength(0);
    pasteEvent({ types: { [TAG_LAYERS_MIME]: 'sheet:a' } });
    expect(state.a).toHaveLength(1);
  });

  it('a layer copied on one page pastes onto another page once that page is active', () => {
    const state: Record<string, TagLayer[]> = {};
    const { rerender } = render(<TwoPages state={state} active="a" />);
    fireEvent.click(screen.getByTestId('layer-a1'));
    fireEvent.keyDown(window, { key: 'c', ctrlKey: true });
    rerender(<TwoPages state={state} active="b" />);
    pasteEvent({ types: { [TAG_LAYERS_MIME]: 'sheet:a' } });
    expect(state.b).toHaveLength(2);
    expect(state.a).toHaveLength(1);
  });

  it('a screenshot pasted from the OS clipboard becomes an image layer on the active page', async () => {
    const state: Record<string, TagLayer[]> = {};
    render(<TwoPages state={state} active="b" />);
    pasteEvent({ files: [png()] });
    await waitFor(() => expect(state.b).toHaveLength(2));
    expect(uploadAsset).toHaveBeenCalledTimes(1);
    expect(state.b[1]).toMatchObject({ type: 'image' });
    expect(state.a).toHaveLength(1);
  });

  it('a read-only page answers no shortcut and no paste', () => {
    const state: Record<string, TagLayer[]> = {};
    render(<TwoPages state={state} active="a" readOnly />);
    fireEvent.click(screen.getByTestId('layer-a1'));
    fireEvent.keyDown(window, { key: 'd', ctrlKey: true });
    pasteEvent({ types: { 'text/plain': 'hello' } });
    expect(state.a ?? [shape('a1')]).toHaveLength(1);
  });

  it('Delete removes the selected layer on the active page', () => {
    const state: Record<string, TagLayer[]> = {};
    render(<TwoPages state={state} active="a" />);
    fireEvent.click(screen.getByTestId('layer-a1'));
    fireEvent.keyDown(window, { key: 'Delete' });
    expect(state.a).toHaveLength(0);
  });
});

describe('context menu Paste reads the system clipboard (both designers)', () => {
  function rightClickEmpty(container: HTMLElement) {
    const stageHost = container.querySelector('[data-konva="stage"]')!.parentElement!.parentElement!;
    fireEvent.contextMenu(stageHost, { clientX: 900, clientY: 900 });
  }

  function stubClipboardRead(items: Array<{ types: string[]; get: (t: string) => Blob }>) {
    const read = vi.fn(async () =>
      items.map((item) => ({ types: item.types, getType: async (t: string) => item.get(t) })),
    );
    Object.defineProperty(navigator, 'clipboard', {
      value: { read, writeText: vi.fn(async () => {}) },
      configurable: true,
    });
    return read;
  }

  afterEach(() => {
    delete (navigator as unknown as { clipboard?: unknown }).clipboard;
  });

  it('Paste is offered with nothing copied in the editor, and a screenshot there is pasted', async () => {
    const read = stubClipboardRead([{ types: ['image/png'], get: () => png() }]);
    const state: { latest: TagLayer[] } = { latest: [] };
    const { container } = render(
      <TagCanvasEditor
        doc={docWith(shape('l1'))}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          state.latest = layers;
        }}
      />,
    );
    rightClickEmpty(container);
    const item = screen.getByRole('menuitem', { name: /Paste/ });
    expect(item).not.toHaveAttribute('data-disabled');
    fireEvent.click(item);
    await waitFor(() => expect(state.latest).toHaveLength(2));
    expect(read).toHaveBeenCalled();
    expect(uploadAsset).toHaveBeenCalledTimes(1);
  });

  it('with layers copied in the editor and the same words on the clipboard, Paste pastes the layers', async () => {
    stubClipboardRead([]);
    setTagClipboard({ layers: [shape('l1')], roots: ['l1'], sourceDocId: null });
    const state: { latest: TagLayer[] } = { latest: [] };
    const { container } = render(
      <TagCanvasEditor
        doc={docWith(shape('l1'))}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          state.latest = layers;
        }}
      />,
    );
    rightClickEmpty(container);
    fireEvent.click(screen.getByRole('menuitem', { name: /Paste/ }));
    await waitFor(() => expect(state.latest).toHaveLength(2));
    expect(uploadAsset).not.toHaveBeenCalled();
  });

  it('the same menu on an active spec sheet page pastes onto that page', async () => {
    stubClipboardRead([{ types: ['text/plain'], get: () => new Blob(['Promo'], { type: 'text/plain' }) }]);
    const state: Record<string, TagLayer[]> = {};
    render(<TwoPages state={state} active="a" />);
    const pageA = screen.getByTestId('page-a');
    rightClickEmpty(pageA);
    fireEvent.click(screen.getByRole('menuitem', { name: /Paste/ }));
    await waitFor(() => expect(state.a).toHaveLength(2));
    expect(state.a[1]).toMatchObject({ type: 'text' });
  });
});
