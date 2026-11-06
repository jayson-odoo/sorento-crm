/**
 * PRICETAG-COMBO-FORMAT R16: double-clicking a text layer bound to a description slot
 * (`combo_description`, `price_tag_description`) that holds rich HTML opens the inline editor
 * READ-ONLY on the plain text (`richPlainText`), never on markup, and never writes anything back to
 * the layer. A plain unbound text layer still opens the normal editable inline editor.
 *
 * Written test-FIRST: today the bound layer's `text_override` HTML opens in an editable textarea,
 * and a blur would save the typed markup over the binding.
 * Reading (flagged): the read-only view is the inline editor itself (`inline-text-editor`, the way
 * the sole-token layer already opens read-only), not a separate element.
 * Stand-ins as in `TagCanvasEditor.inline-edit.test.tsx`.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  LineTagData,
  TagBindingData,
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

const HTML = '<p><strong>SRTBF11416</strong> (CABINET)</p><p>L400xW345xH390mm</p>';
const PLAIN = 'SRTBF11416 (CABINET)\nL400xW345xH390mm';

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

describe('inline edit of a description-bound layer (R16)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  for (const slot of ['combo_description', 'price_tag_description']) {
    it(`R16: ${slot} opens read-only on the plain text, not the markup`, async () => {
      const onChange = vi.fn();
      render(<TagCanvasEditor doc={docWith(layerWith('d', slot, '', HTML))} onChange={onChange} />);

      fireEvent.doubleClick(screen.getByTestId('layer-d'));
      const editor = (await screen.findByTestId('inline-text-editor')) as HTMLTextAreaElement;

      expect(editor.readOnly).toBe(true);
      expect(editor.value).toBe(PLAIN);
      expect(editor.value).not.toContain('<');
    });

    it(`R16: ${slot} writes nothing to the layer, however the editor is left`, async () => {
      const onChange = vi.fn();
      render(<TagCanvasEditor doc={docWith(layerWith('d', slot, '', HTML))} onChange={onChange} />);

      fireEvent.doubleClick(screen.getByTestId('layer-d'));
      const editor = await screen.findByTestId('inline-text-editor');
      // A read-only box ignores typing in a browser; fireEvent does not, so the change is forced to
      // prove the editor itself never commits it.
      fireEvent.change(editor, { target: { value: 'typed over it' } });
      fireEvent.keyDown(editor, { key: 'Escape' });
      fireEvent.blur(editor);

      await waitFor(() => expect(screen.queryByTestId('inline-text-editor')).toBeNull());
      expect(onChange).not.toHaveBeenCalled();
      // ...and the layer on the canvas still holds the stored markup, not the typed text.
      expect(screen.getByTestId('layer-d')).not.toHaveTextContent('typed over it');
    });
  }

  it('R16: a plain unbound text layer still opens the normal editable inline editor', async () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={docWith(layerWith('p', null, 'Original', null))} onChange={onChange} />);

    fireEvent.doubleClick(screen.getByTestId('layer-p'));
    const editor = (await screen.findByTestId('inline-text-editor')) as HTMLTextAreaElement;

    expect(editor.readOnly).toBe(false);
    expect(editor.value).toBe('Original');
    fireEvent.change(editor, { target: { value: 'Edited' } });
    fireEvent.blur(editor);
    await waitFor(() => expect(screen.getByTestId('layer-p')).toHaveTextContent('Edited'));
  });
});

// DESIGNER-RICH-TEXT: a layer whose OWN content is formatted is edited in the Inspector's rich
// Content box. The plain canvas editor shows its text read-only and never writes plain text over
// the marks; Cmd+B typed in the Content box formats the selection there, never the whole layer.
describe('a layer with formatted own content (DESIGNER-RICH-TEXT)', () => {
  const OWN = '<p><strong>{{product.code}}</strong></p><p>LP</p>';

  it('double-click opens the inline editor read-only on the plain text', async () => {
    render(<TagCanvasEditor doc={docWith(layerWith('r', null, OWN, null))} onChange={vi.fn()} />);

    fireEvent.doubleClick(screen.getByTestId('layer-r'));
    const editor = (await screen.findByTestId('inline-text-editor')) as HTMLTextAreaElement;

    expect(editor.readOnly).toBe(true);
    expect(editor.value).toBe('{{product.code}}\nLP');
  });

  it('leaving the inline editor writes nothing over the formatted content', async () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={docWith(layerWith('r', null, OWN, null))} onChange={onChange} />);

    fireEvent.doubleClick(screen.getByTestId('layer-r'));
    const editor = await screen.findByTestId('inline-text-editor');
    fireEvent.change(editor, { target: { value: 'typed over it' } });
    fireEvent.blur(editor);
    await waitFor(() => expect(screen.queryByTestId('inline-text-editor')).toBeNull());

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const saved = onChange.mock.calls.at(-1)![0] as TagTemplateDoc;
    const layer = saved.layers.find((l) => l.id === 'r')!;
    expect(layer.props.kind === 'text' && layer.props.text).toBe(OWN);
  });

  it('Cmd+B with focus in the Inspector Content box does not bold the whole layer', async () => {
    const onChange = vi.fn();
    const { container } = render(
      <TagCanvasEditor doc={docWith(layerWith('p', null, 'Plain', null))} onChange={onChange} />,
    );
    fireEvent.click(screen.getByTestId('layer-p'));
    const box = await waitFor(() => {
      const el = container.querySelector<HTMLElement>('.ProseMirror');
      expect(el).not.toBeNull();
      return el!;
    });
    box.focus();
    expect(document.activeElement).toBe(box);
    fireEvent.keyDown(box, { key: 'b', metaKey: true, bubbles: true });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const saved = onChange.mock.calls.at(-1)![0] as TagTemplateDoc;
    const layer = saved.layers.find((l) => l.id === 'p')!;
    expect(layer.props.kind === 'text' && layer.props.fontWeight).toBe(defaultTextProps().fontWeight);
  });
});
