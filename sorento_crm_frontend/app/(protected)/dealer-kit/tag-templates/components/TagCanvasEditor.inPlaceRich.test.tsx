/**
 * DESIGNER-RICH-TEXT owner hand test, 6 Nov (FAIL 1): double-clicking into a text box on the
 * CANVAS, highlighting only the 2nd line ({{combo.description}}) and pressing Cmd+B bolded the
 * WHOLE box. The in-place editor is now the same rich model as the Inspector's Content box: a
 * key on a canvas selection marks only that range, and the layer-level weight is untouched.
 *
 * Written test-FIRST: today the in-place editor is a plain textarea and Cmd+B reaches the
 * canvas's whole-layer format.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  TagLayer,
  TagTemplateDoc,
} from '@/lib/dealer-kit/tag-template-types';
import { defaultTextProps } from '@/lib/dealer-kit/tag-template-types';

// -- Stand-ins for everything that needs a browser or a server ---------------

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
    Line: passthrough('line'),
    Transformer: passthrough('transformer'),
  };
});

vi.mock('./KonvaTagLayer', () => ({
  KonvaTagLayer: ({
    layer,
    display,
    onSelect,
    onDoubleClick,
  }: {
    layer: TagLayer;
    display?: { text?: string };
    onSelect?: (id: string, additive: boolean) => void;
    onDoubleClick?: (id: string) => void;
  }) => (
    <div
      data-testid={`layer-${layer.id}`}
      onClick={() => onSelect?.(layer.id, false)}
      onDoubleClick={() => onDoubleClick?.(layer.id)}
    >
      {display?.text ?? ''}
    </div>
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

// -- The document under test -------------------------------------------------


function layerWith(id: string, slot: string | null, text: string, override: string | null): TagLayer {
  return {
    id,
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 20,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: slot as TagLayer['slot_binding'],
    text_override: override,
    props: { ...defaultTextProps(), text },
  };
}

function docWith(layer: TagLayer): TagTemplateDoc {
  return { width_mm: 60, height_mm: 40, layers: [layer] };
}

const OWNER = '{{product.code}}\n{{combo.description}}\nLP: {{product.list_price}}';

/** The in-place rich editor's TipTap instance (TipTap stores it on its own DOM element). */
async function inPlaceEditor(): Promise<{ dom: HTMLElement; editor: import('@tiptap/react').Editor }> {
  const host = await screen.findByTestId('inline-rich-editor');
  const dom = await waitFor(() => {
    const el = host.querySelector<HTMLElement>('.ProseMirror');
    expect(el).not.toBeNull();
    return el!;
  });
  const editor = (dom as unknown as { editor: import('@tiptap/react').Editor }).editor;
  return { dom, editor };
}

function savedLayer(onChange: ReturnType<typeof vi.fn>, id: string): TagLayer {
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  const saved = onChange.mock.calls.at(-1)![0] as TagTemplateDoc;
  return saved.layers.find((l) => l.id === id)!;
}

describe('in-place canvas editing is per-selection rich text (owner hand test FAIL 1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('double-click opens the rich editor on the content, tokens as chips', async () => {
    render(<TagCanvasEditor doc={docWith(layerWith('t', null, OWNER, null))} onChange={vi.fn()} />);
    fireEvent.doubleClick(screen.getByTestId('layer-t'));

    const { dom } = await inPlaceEditor();
    expect(Array.from(dom.querySelectorAll('p')).map((p) => p.textContent)).toEqual(OWNER.split('\n'));
    expect(dom.querySelectorAll('[data-merge-field]')).toHaveLength(3);
    expect(screen.queryByRole('textbox', { name: 'Edit text' })?.tagName).not.toBe('TEXTAREA');
  });

  it('select only line 2, Cmd+B: only {{combo.description}} is bold, the layer weight is untouched', async () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={docWith(layerWith('t', null, OWNER, null))} onChange={onChange} />);
    fireEvent.doubleClick(screen.getByTestId('layer-t'));
    const { dom, editor } = await inPlaceEditor();

    // Line 2 is the paragraph holding the combo description token alone.
    let from = 0;
    let to = 0;
    editor.state.doc.forEach((node, offset, index) => {
      if (index === 1) {
        from = offset + 1;
        to = offset + node.nodeSize - 1;
      }
    });
    editor.chain().focus().setTextSelection({ from, to }).run();
    // jsdom is not macOS, so the editor's Mod key is Ctrl (Cmd on a Mac).
    fireEvent.keyDown(dom, { key: 'b', code: 'KeyB', ctrlKey: true, bubbles: true });
    fireEvent.keyDown(dom, { key: 'Escape', bubbles: true });

    await waitFor(() => expect(screen.queryByTestId('inline-rich-editor')).toBeNull());
    const layer = savedLayer(onChange, 't');
    expect(layer.props.kind === 'text' && layer.props.text).toBe(
      '<p>{{product.code}}</p><p><strong>{{combo.description}}</strong></p><p>LP: {{product.list_price}}</p>',
    );
    expect(layer.props.kind === 'text' && layer.props.fontWeight).toBe(defaultTextProps().fontWeight);
  });

  it('typing in place with no formatting keeps the plain format', async () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={docWith(layerWith('t', null, 'Hello', null))} onChange={onChange} />);
    fireEvent.doubleClick(screen.getByTestId('layer-t'));
    const { dom, editor } = await inPlaceEditor();

    editor.chain().focus('end').insertContent('!').run();
    fireEvent.keyDown(dom, { key: 'Escape', bubbles: true });

    await waitFor(() => expect(screen.queryByTestId('inline-rich-editor')).toBeNull());
    expect(savedLayer(onChange, 't').props).toMatchObject({ text: 'Hello!' });
  });

  it('opening and leaving with no edit writes nothing (B2)', async () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={docWith(layerWith('t', null, OWNER, null))} onChange={onChange} />);
    fireEvent.doubleClick(screen.getByTestId('layer-t'));
    const { dom } = await inPlaceEditor();
    fireEvent.keyDown(dom, { key: 'Escape', bubbles: true });

    await waitFor(() => expect(screen.queryByTestId('inline-rich-editor')).toBeNull());
    expect(savedLayer(onChange, 't').props).toMatchObject({ text: OWNER });
  });

  it('formatted content opens in place WITH its formatting and stays editable', async () => {
    const own = '<p><strong>{{product.code}}</strong></p><p>LP</p>';
    render(<TagCanvasEditor doc={docWith(layerWith('t', null, own, null))} onChange={vi.fn()} />);
    fireEvent.doubleClick(screen.getByTestId('layer-t'));
    const { dom } = await inPlaceEditor();

    expect(dom.querySelector('strong [data-merge-field="product.code"]')).not.toBeNull();
    expect(dom.getAttribute('contenteditable')).toBe('true');
  });

  it('a slot-bound layer edited in place writes text_override, binding kept', async () => {
    const onChange = vi.fn();
    render(
      <TagCanvasEditor doc={docWith(layerWith('t', 'code', '', 'Code {{product.code}}'))} onChange={onChange} />,
    );
    fireEvent.doubleClick(screen.getByTestId('layer-t'));
    const { dom, editor } = await inPlaceEditor();
    editor.chain().focus().selectAll().toggleBold().run();
    fireEvent.keyDown(dom, { key: 'Escape', bubbles: true });

    await waitFor(() => expect(screen.queryByTestId('inline-rich-editor')).toBeNull());
    const layer = savedLayer(onChange, 't');
    expect(layer.slot_binding).toBe('code');
    expect(layer.text_override).toBe('<p><strong>Code {{product.code}}</strong></p>');
  });
});
