/**
 * SPEC-SHEET-PARITY-B2 v3 editor, C7: keyboard Delete on a spec sheet page, like Google Slides.
 *
 * - AC-C7.1: with a layer selected on the ACTIVE embedded page, Delete or Backspace removes it, even
 *   when focus sits on a toolbar button (the last thing clicked); other pages are untouched.
 * - AC-C7.2: not while typing: a keydown in an input, a textarea or a contenteditable (cell editor,
 *   text editor, Inspector) edits the text only.
 *
 * The plan notes `TagCanvasEditor` already deletes when `shortcutsLive`; these pin it on the
 * embedded page so the reader-level fix cannot regress it.
 */
import * as React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { defaultShapeProps } from '@/lib/dealer-kit/tag-template-types';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    Stage: ({ children, ref }: { children?: React.ReactNode; ref?: React.Ref<{ getContent: () => HTMLElement }> }) => {
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
  KonvaTagLayer: ({ layer, onSelect }: { layer: TagLayer; onSelect?: (id: string, additive: boolean) => void }) => (
    <div data-testid={`layer-${layer.id}`} onClick={() => onSelect?.(layer.id, false)} />
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
  uploadAsset: vi.fn(),
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

// jsdom does not implement `isContentEditable`; a browser does. Mirror the browser so the
// contenteditable case tests the product, not the test DOM.
if (!('isContentEditable' in HTMLElement.prototype) || document.createElement('div').isContentEditable === undefined) {
  Object.defineProperty(HTMLElement.prototype, 'isContentEditable', {
    configurable: true,
    get(this: HTMLElement) {
      return Boolean(this.closest('[contenteditable=""], [contenteditable="true"]'));
    },
  });
}

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

/** Two pages like the reader, plus the kinds of field a user types in beside them. */
function Reader({ state }: { state: Record<string, TagLayer[]> }) {
  const [selected, setSelected] = React.useState<{ page: string; id: string | null }>({ page: 'a', id: null });
  const page = (key: 'a' | 'b') => {
    const embedded: EmbeddedMode = {
      pxPerMm: 2,
      selectedLayerId: selected.page === key ? selected.id : null,
      onSelect: (id) => setSelected({ page: key, id }),
      controllerRef: { current: null },
      active: key === 'a',
      readOnly: false,
    };
    return (
      <TagCanvasEditor
        key={key}
        doc={{ width_mm: 100, height_mm: 60, layers: [shape(`${key}1`)] }}
        onChange={vi.fn()}
        docId={`sheet:${key}`}
        specSheet
        embedded={embedded}
        onLayersChange={(layers) => {
          state[key] = layers;
        }}
      />
    );
  };
  return (
    <>
      <button type="button">Add Text</button>
      <input aria-label="Font size" defaultValue="12" />
      <textarea aria-label="Comment" defaultValue="note" />
      <div aria-label="Cell editor" contentEditable suppressContentEditableWarning>
        REF
      </div>
      {page('a')}
      {page('b')}
    </>
  );
}

function selectOnA() {
  const state: Record<string, TagLayer[]> = {};
  render(<Reader state={state} />);
  fireEvent.click(screen.getByTestId('layer-a1'));
  return state;
}

describe('Delete / Backspace on the active spec sheet page (AC-C7.1)', () => {
  it('Backspace removes the selected layer', () => {
    const state = selectOnA();
    fireEvent.keyDown(window, { key: 'Backspace' });
    expect(state.a).toHaveLength(0);
    expect(state.b ?? [shape('b1')]).toHaveLength(1);
  });

  it('Delete removes it while focus sits on a toolbar button', () => {
    const state = selectOnA();
    const button = screen.getByRole('button', { name: 'Add Text' });
    button.focus();
    fireEvent.keyDown(button, { key: 'Delete', bubbles: true });
    expect(state.a).toHaveLength(0);
  });
});

describe('not while typing (AC-C7.2)', () => {
  it.each([
    ['an input', () => screen.getByLabelText('Font size')],
    ['a textarea', () => screen.getByLabelText('Comment')],
    ['a contenteditable cell editor', () => screen.getByLabelText('Cell editor')],
  ])('Delete and Backspace inside %s leave the layer', (_name, field) => {
    const state = selectOnA();
    const el = field() as HTMLElement;
    el.focus();
    fireEvent.keyDown(el, { key: 'Delete', bubbles: true });
    fireEvent.keyDown(el, { key: 'Backspace', bubbles: true });
    expect(state.a ?? [shape('a1')]).toHaveLength(1);
  });
});
