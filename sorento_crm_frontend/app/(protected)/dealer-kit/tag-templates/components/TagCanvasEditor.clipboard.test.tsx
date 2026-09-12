/**
 * Clipboard across a remount - lines, pages, and the template editor (S3,
 * PLAN D3, AC-S3-1/2/3/4).
 *
 * `clipboard` used to be `useState` inside the editor, and the request
 * designer remounts `TagCanvasEditor` with `key={selectedTag.id}` on every
 * line switch (a fresh `key` unmounts the old instance and mounts a new
 * one) - so copying on line A and clicking line B emptied the clipboard
 * before Paste ever ran. `lib/dealer-kit/tag-clipboard.ts` moves the value
 * to module scope so it survives exactly that; this file drives it through
 * `TagCanvasEditor`'s own `docId` prop, unmounting and remounting the way
 * the request designer actually does.
 *
 * `tag-clipboard.test.ts` pins the store itself in isolation; this is the
 * WIRING - Ctrl+C/X/V through to `handleCopy`/`handleCut`/`handlePaste`, and
 * which offset a paste gets depending on whether `docId` matches.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultShapeProps } from '@/lib/dealer-kit/tag-template-types';
import { setTagClipboard } from '@/lib/dealer-kit/tag-clipboard';

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
  }) => <div data-testid={`layer-${layer.id}`} onClick={() => onSelect?.(layer.id, false)} />,
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

function shapeLayer(id: string, overrides: Partial<TagLayer> = {}): TagLayer {
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
  return { width_mm: 60, height_mm: 40, layers };
}

function selectLayer(id: string) {
  fireEvent.click(screen.getByTestId(`layer-${id}`));
}

function copy() {
  fireEvent.keyDown(window, { key: 'c', ctrlKey: true });
}

function cut() {
  fireEvent.keyDown(window, { key: 'x', ctrlKey: true });
}

function paste() {
  fireEvent.keyDown(window, { key: 'v', ctrlKey: true });
}

afterEach(() => {
  setTagClipboard(null);
});

describe('TagCanvasEditor clipboard across a remount (S3, AC-S3-1/2)', () => {
  it('copies on one instance, pastes at the ORIGINAL x/y once remounted on a DIFFERENT doc', () => {
    // Line A: copy, then unmount (as the request designer's `key` change does
    // on switching lines).
    const { unmount } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('l1'))} onChange={vi.fn()} docId="tag-a" />,
    );
    selectLayer('l1');
    copy();
    unmount();

    // Line B: a FRESH instance, different docId, no shared React tree at all.
    let latest: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('other', { x_mm: 0, y_mm: 0 }))}
        onChange={vi.fn()}
        docId="tag-b"
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );
    paste();

    const pasted = latest.find((l) => l.id !== 'other')!;
    expect(pasted).toBeDefined();
    // Cross-doc paste: the ORIGINAL x/y, not offset - a layout copied from
    // another line has to land in the same place to be useful.
    expect(pasted.x_mm).toBe(10);
    expect(pasted.y_mm).toBe(10);
  });

  it('pastes offset by 5mm when the doc is the SAME one the copy came from (AC-S3-3)', () => {
    let latest: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('l1'))}
        onChange={vi.fn()}
        docId="tag-a"
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );
    selectLayer('l1');
    copy();
    paste();

    const pasted = latest.find((l) => l.id !== 'l1')!;
    expect(pasted.x_mm).toBe(15);
    expect(pasted.y_mm).toBe(15);
  });

  it('pastes unoffset when neither render names a docId (bare test render, sourceDocId null both times)', () => {
    let latest: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('l1'))}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );
    selectLayer('l1');
    copy();
    paste();

    // null === null: this counts as "the same doc" (AC-S3-3's "or neither
    // side names one"), so it offsets like a duplicate, not a cross-doc land.
    const pasted = latest.find((l) => l.id !== 'l1')!;
    expect(pasted.x_mm).toBe(15);
  });

  it('Cut copies then removes the selection, and survives the same remount (AC-S3-4)', () => {
    const { unmount } = render(
      <TagCanvasEditor doc={docWith(shapeLayer('l1'))} onChange={vi.fn()} docId="tag-a" />,
    );
    selectLayer('l1');
    cut();
    unmount();

    let latest: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('other', { x_mm: 0, y_mm: 0 }))}
        onChange={vi.fn()}
        docId="tag-b"
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );
    paste();

    const pasted = latest.find((l) => l.id !== 'other')!;
    expect(pasted).toBeDefined();
    expect(pasted.x_mm).toBe(10);
  });

  it('an empty clipboard (a fresh session, or after a reload) leaves Paste a no-op', () => {
    setTagClipboard(null);
    let latest: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('l1'))}
        onChange={vi.fn()}
        docId="tag-a"
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );

    paste();

    expect(latest.filter((l) => l.id !== 'l1')).toHaveLength(0);
  });
});
