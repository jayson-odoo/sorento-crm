/**
 * PRICETAG-DESIGNER-FEEDBACK AC-4.2 / AC-4.4 / AC-4.5 end to end (owner hand test 14 Nov): with the
 * Inspector's rich Content editor open and the caret after "RM ", Insert field opens on the
 * element's EXISTING text, and Done puts only the picked field in at that caret, inside the bold
 * run, changing nothing else.
 *
 * Written test-FIRST. The dialog side of the contract (`context: { before, after }`, Done returns
 * only the picked tokens) is pinned in InsertFieldDialog.existing-content.test.tsx; this file pins
 * that the editor hands the dialog the text around the caret and inserts what comes back there.
 * Stand-ins as in TagCanvasEditor.richInline.test.tsx.
 */
import '@/test-utils/prosemirrorGeometry';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { Editor } from '@tiptap/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultTextProps } from '@/lib/dealer-kit/tag-template-types';

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

const CONTENT = '<p>{{combo.description}}</p><p><strong>LP: RM {{product.list_price}}</strong></p>';

function textLayer(): TagLayer {
  return {
    id: 't',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 20,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultTextProps(), text: CONTENT },
  };
}

function docWith(layer: TagLayer): TagTemplateDoc {
  return { width_mm: 60, height_mm: 40, layers: [layer] };
}

/** Selects the layer, waits for the Inspector's rich Content box, puts the caret after "RM ". */
async function openContentAtCaret(container: HTMLElement): Promise<Editor> {
  fireEvent.click(screen.getByTestId('layer-t'));
  const dom = await waitFor(() => {
    const el = container.querySelector<HTMLElement>('.ProseMirror');
    expect(el).not.toBeNull();
    return el!;
  });
  const editor = (dom as unknown as { editor: Editor }).editor;
  let caret = -1;
  editor.state.doc.descendants((node, pos) => {
    if (caret < 0 && node.isText && node.text?.includes('LP: RM ')) {
      caret = pos + node.text.indexOf('LP: RM ') + 'LP: RM '.length;
    }
  });
  expect(caret, 'found "LP: RM " in the Content box').toBeGreaterThan(0);
  act(() => {
    editor.chain().focus().setTextSelection(caret).run();
  });
  return editor;
}

function dialogContentText(): string {
  const dialog = screen.getByRole('dialog');
  const box = dialog.querySelector('#merge-field-content') as HTMLElement | null;
  expect(box, 'the dialog Content box').not.toBeNull();
  return box instanceof HTMLTextAreaElement ? box.value : box!.textContent ?? '';
}

/** The dialog Content text before and after its `[data-testid="insert-point"]` marker. */
function dialogAroundInsertPoint(): { before: string; after: string } {
  const box = screen.getByRole('dialog').querySelector('#merge-field-content') as HTMLElement;
  const marker = box.querySelector('[data-testid="insert-point"]');
  expect(marker, 'an insert point inside the dialog Content box').not.toBeNull();
  let before = '';
  let after = '';
  const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (marker!.contains(node)) continue;
    if (marker!.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_PRECEDING) before += node.textContent ?? '';
    else after += node.textContent ?? '';
  }
  return { before, after };
}

function storedText(latest: TagLayer[]): string {
  const layer = latest.find((l) => l.id === 't')!;
  return layer.props.kind === 'text' ? layer.props.text : '';
}

describe('Insert field from the rich Content box (AC-4)', () => {
  it('AC-4.2: the dialog opens on the existing text of both lines, not empty', async () => {
    const { container } = render(<TagCanvasEditor doc={docWith(textLayer())} onChange={vi.fn()} />);
    await openContentAtCaret(container);

    fireEvent.click(screen.getByRole('button', { name: /Insert field/ }));
    await screen.findByRole('dialog');

    const text = dialogContentText();
    expect(text).not.toBe('');
    expect(text).toContain('{{combo.description}}');
    expect(text).toContain('LP: RM ');
    expect(text).toContain('{{product.list_price}}');
    // The insert point is at the caret: right after "RM ", right before the price token.
    const around = dialogAroundInsertPoint();
    expect(around.before.endsWith('LP: RM ')).toBe(true);
    expect(around.after.startsWith('{{product.list_price}}')).toBe(true);
  });

  it('AC-4.4: Done inserts only the picked field at the caret, inside the bold run', async () => {
    let latest: TagLayer[] = [];
    const { container } = render(
      <TagCanvasEditor
        doc={docWith(textLayer())}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );
    await openContentAtCaret(container);

    fireEvent.click(screen.getByRole('button', { name: /Insert field/ }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByText('{{product.code}}').closest('button')!);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));

    await waitFor(() =>
      expect(storedText(latest)).toBe(
        '<p>{{combo.description}}</p><p><strong>LP: RM {{product.code}}{{product.list_price}}</strong></p>',
      ),
    );
  });

  it('AC-4.4: two picks go in at the caret, in order', async () => {
    let latest: TagLayer[] = [];
    const { container } = render(
      <TagCanvasEditor
        doc={docWith(textLayer())}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );
    await openContentAtCaret(container);

    fireEvent.click(screen.getByRole('button', { name: /Insert field/ }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByText('{{product.code}}').closest('button')!);
    fireEvent.click(within(dialog).getByText('{{product.name}}').closest('button')!);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));

    await waitFor(() =>
      expect(storedText(latest)).toBe(
        '<p>{{combo.description}}</p><p><strong>LP: RM {{product.code}}{{product.name}}{{product.list_price}}</strong></p>',
      ),
    );
  });

  it('AC-4.5: Cancel changes nothing', async () => {
    let latest: TagLayer[] = [];
    const { container } = render(
      <TagCanvasEditor
        doc={docWith(textLayer())}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );
    await openContentAtCaret(container);

    fireEvent.click(screen.getByRole('button', { name: /Insert field/ }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByText('{{product.code}}').closest('button')!);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const stored = latest.length ? storedText(latest) : CONTENT;
    expect(stored).toBe(CONTENT);
  });
});
