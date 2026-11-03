/**
 * Ctrl+V from the SYSTEM clipboard (DESIGNER-PASTE, PLAN-designer-paste-03nov.md).
 *
 * A screenshot or picture pasted into the designer becomes an image layer,
 * uploaded through the same `uploadAsset` call the Image tool's picker uses;
 * pasted text becomes a text layer. The browser's own `paste` event is what
 * carries the clipboard, so these tests dispatch that event, the way a real
 * Ctrl+V does once the keydown is not cancelled.
 */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  TagLayer,
  TagTemplateDoc,
} from '@/lib/dealer-kit/tag-template-types';
import {
  defaultImageProps,
  defaultShapeProps,
} from '@/lib/dealer-kit/tag-template-types';
import { setTagClipboard } from '@/lib/dealer-kit/tag-clipboard';
import { TAG_LAYERS_MIME } from '@/lib/dealer-kit/clipboard-paste';

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
    onSelect,
  }: {
    layer: TagLayer;
    onSelect?: (id: string, additive: boolean) => void;
  }) => (
    <div
      data-testid={`layer-${layer.id}`}
      onClick={() => onSelect?.(layer.id, false)}
    />
  ),
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

const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: Object.assign(vi.fn(), {
    error: (...args: unknown[]) => toastError(...args),
    success: vi.fn(),
    loading: vi.fn(() => 'toast-id'),
    dismiss: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  }),
}));

// jsdom never decodes an image, so the natural size comes from this stand-in.
vi.mock('@/lib/dealer-kit/clipboard-paste', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/lib/dealer-kit/clipboard-paste')>();
  return {
    ...actual,
    readImageSize: vi.fn(async () => ({ width: 1920, height: 1080 })),
  };
});

import { TagCanvasEditor } from './TagCanvasEditor';

function baseLayer(id: string, overrides: Partial<TagLayer> = {}): TagLayer {
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
    ...overrides,
  };
}

function docWith(...layers: TagLayer[]): TagTemplateDoc {
  return { width_mm: 100, height_mm: 150, layers };
}

function pasteEvent(
  opts: { types?: Record<string, string>; files?: File[] },
  target: EventTarget = window,
) {
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
    target.dispatchEvent(event);
  });
  return event;
}

const png = () =>
  new File([new Uint8Array(16)], 'image.png', { type: 'image/png' });

function renderEditor(doc: TagTemplateDoc) {
  const state: { latest: TagLayer[] } = { latest: doc.layers };
  render(
    <TagCanvasEditor
      doc={doc}
      onChange={vi.fn()}
      onLayersChange={(layers) => {
        state.latest = layers;
      }}
    />,
  );
  return state;
}

beforeEach(() => {
  uploadAsset.mockReset();
  uploadAsset.mockResolvedValue({ id: 'asset-new', name: 'Pasted image' });
  toastError.mockReset();
});

afterEach(() => {
  setTagClipboard(null);
});

describe('TagCanvasEditor system clipboard paste', () => {
  it('an image paste uploads it like the image tool and adds a centred image layer that fits (AC-1)', async () => {
    const state = renderEditor(docWith(baseLayer('l1')));
    const file = png();
    const event = pasteEvent({ files: [file] });
    expect(event.defaultPrevented).toBe(true);

    await waitFor(() => expect(state.latest).toHaveLength(2));
    expect(uploadAsset).toHaveBeenCalledTimes(1);
    expect(uploadAsset.mock.calls[0][0]).toMatchObject({
      file,
      kind: 'decorative',
    });

    const added = state.latest.find((l) => l.id !== 'l1')!;
    expect(added.type).toBe('image');
    expect(added.props).toMatchObject({
      kind: 'image',
      source: { type: 'asset', assetId: 'asset-new' },
    });
    // 1920 x 1080 into 100 x 150: bounded by the width.
    expect(added.width_mm).toBeCloseTo(100);
    expect(added.height_mm).toBeCloseTo(56.25);
    expect(added.x_mm).toBeCloseTo(0);
    expect(added.y_mm).toBeCloseTo((150 - 56.25) / 2);
    expect(added.z_index).toBeGreaterThan(1);
  });

  it('with one image layer selected, the paste replaces that layer image in place (AC-2)', async () => {
    const image = baseLayer('img', {
      type: 'image',
      props: {
        ...defaultImageProps(),
        source: { type: 'asset', assetId: 'old' },
      },
    });
    const state = renderEditor(docWith(image));
    fireEvent.click(screen.getByTestId('layer-img'));
    pasteEvent({ files: [png()] });

    await waitFor(() =>
      expect(state.latest[0].props).toMatchObject({
        source: { type: 'asset', assetId: 'asset-new' },
      }),
    );
    expect(state.latest).toHaveLength(1);
    expect(state.latest[0]).toMatchObject({
      id: 'img',
      x_mm: 10,
      y_mm: 10,
      width_mm: 20,
      height_mm: 10,
    });
  });

  it('pasted text becomes a text layer holding that text (AC-3)', () => {
    const state = renderEditor(docWith(baseLayer('l1')));
    pasteEvent({ types: { 'text/plain': 'Promo 20% off' } });
    const added = state.latest.find((l) => l.id !== 'l1')!;
    expect(added.type).toBe('text');
    expect(added.props).toMatchObject({ kind: 'text', text: 'Promo 20% off' });
    expect(uploadAsset).not.toHaveBeenCalled();
  });

  it('a paste with focus inside an input is left to the browser (AC-4)', () => {
    const state = renderEditor(docWith(baseLayer('l1')));
    const input = document.createElement('input');
    document.body.appendChild(input);
    try {
      input.focus();
      const event = pasteEvent(
        { types: { 'text/plain': 'typed' }, files: [png()] },
        input,
      );
      expect(event.defaultPrevented).toBe(false);
      expect(state.latest).toHaveLength(1);
      expect(uploadAsset).not.toHaveBeenCalled();
    } finally {
      input.remove();
    }
  });

  it('Ctrl+Z undoes an image paste in one step (AC-5)', async () => {
    const state = renderEditor(docWith(baseLayer('l1')));
    pasteEvent({ files: [png()] });
    await waitFor(() => expect(state.latest).toHaveLength(2));
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
    expect(state.latest.map((l) => l.id)).toEqual(['l1']);
  });

  it('Ctrl+Z undoes a text paste in one step (AC-5)', () => {
    const state = renderEditor(docWith(baseLayer('l1')));
    pasteEvent({ types: { 'text/plain': 'hello' } });
    expect(state.latest).toHaveLength(2);
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
    expect(state.latest.map((l) => l.id)).toEqual(['l1']);
  });

  it('an unsupported image type is refused with a toast and nothing uploads (AC-6)', () => {
    const state = renderEditor(docWith(baseLayer('l1')));
    pasteEvent({ files: [new File(['x'], 'a.gif', { type: 'image/gif' })] });
    expect(uploadAsset).not.toHaveBeenCalled();
    expect(toastError).toHaveBeenCalled();
    expect(state.latest).toHaveLength(1);
  });

  it('a failed upload toasts and leaves the canvas as it was', async () => {
    uploadAsset.mockRejectedValueOnce(new Error('File too large'));
    const state = renderEditor(docWith(baseLayer('l1')));
    pasteEvent({ files: [png()] });
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith('File too large'),
    );
    expect(state.latest).toHaveLength(1);
  });

  it('Ctrl+C writes the editor marker on the copy event, and a paste carrying it pastes the layers (AC-7)', () => {
    const state = renderEditor(docWith(baseLayer('l1')));
    fireEvent.click(screen.getByTestId('layer-l1'));
    fireEvent.keyDown(window, { key: 'c', ctrlKey: true });

    const written: Record<string, string> = {};
    const copy = new Event('copy', { bubbles: true, cancelable: true });
    Object.defineProperty(copy, 'clipboardData', {
      value: {
        setData: (type: string, value: string) => (written[type] = value),
      },
    });
    act(() => {
      window.dispatchEvent(copy);
    });
    expect(copy.defaultPrevented).toBe(true);
    expect(written[TAG_LAYERS_MIME]).toBeTruthy();

    pasteEvent({ types: { [TAG_LAYERS_MIME]: written[TAG_LAYERS_MIME] } });
    expect(state.latest).toHaveLength(2);
    expect(state.latest[1]).toMatchObject({
      type: 'shape',
      x_mm: 15,
      y_mm: 15,
    });
  });

  it('a copy event with nothing copied in the editor is left alone', () => {
    renderEditor(docWith(baseLayer('l1')));
    const copy = new Event('copy', { bubbles: true, cancelable: true });
    Object.defineProperty(copy, 'clipboardData', {
      value: { setData: vi.fn() },
    });
    act(() => {
      window.dispatchEvent(copy);
    });
    expect(copy.defaultPrevented).toBe(false);
  });

  it('the Ctrl+V keydown is not cancelled, so the browser goes on to fire the paste event', () => {
    renderEditor(docWith(baseLayer('l1')));
    const keydown = new KeyboardEvent('keydown', {
      key: 'v',
      ctrlKey: true,
      cancelable: true,
    });
    act(() => {
      window.dispatchEvent(keydown);
    });
    expect(keydown.defaultPrevented).toBe(false);
  });

  it('names a pasted screenshot after the paste, not the generic image.png', async () => {
    renderEditor(docWith(baseLayer('l1')));
    pasteEvent({ files: [png()] });
    await waitFor(() => expect(uploadAsset).toHaveBeenCalledTimes(1));
    expect(uploadAsset.mock.calls[0][0].name).toMatch(/^Pasted image /);
  });

  it('cancels beforepaste on the canvas (WebKit only fires paste on a non-editable page then)', () => {
    renderEditor(docWith(baseLayer('l1')));
    const event = new Event('beforepaste', { bubbles: true, cancelable: true });
    act(() => {
      window.dispatchEvent(event);
    });
    expect(event.defaultPrevented).toBe(true);
  });

  it('leaves beforepaste alone inside an input', () => {
    renderEditor(docWith(baseLayer('l1')));
    const input = document.createElement('input');
    document.body.appendChild(input);
    try {
      input.focus();
      const event = new Event('beforepaste', {
        bubbles: true,
        cancelable: true,
      });
      act(() => {
        input.dispatchEvent(event);
      });
      expect(event.defaultPrevented).toBe(false);
    } finally {
      input.remove();
    }
  });

  it('the Ctrl+V keydown alone pastes nothing: the paste event does (no race with a late macOS paste)', async () => {
    const state = renderEditor(docWith(baseLayer('l1')));
    fireEvent.click(screen.getByTestId('layer-l1'));
    fireEvent.keyDown(window, { key: 'c', ctrlKey: true });
    fireEvent.keyDown(window, { key: 'v', ctrlKey: true });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(state.latest).toHaveLength(1);

    // The paste arriving late (after the keydown's task, as Cmd+V does on a
    // Mac) is still the one paste.
    pasteEvent({ types: { 'text/plain': 'hello' } });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(state.latest).toHaveLength(2);
    expect(state.latest[1].props).toMatchObject({
      kind: 'text',
      text: 'hello',
    });
  });
});
