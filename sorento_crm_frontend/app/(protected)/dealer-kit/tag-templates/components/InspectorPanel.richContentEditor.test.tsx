/**
 * DESIGNER-RICH-TEXT: the Inspector's TEXT > Content box is the shared rich editor (inline toolbar,
 * atomic tokens). Formatting a selection writes rich HTML to the layer; an edit with no
 * formatting keeps the plain text format existing templates use. A bound layer still writes to
 * `text_override`; a description-bound layer keeps its read-only plain box (R8).
 *
 * Written test-FIRST: today the Content box is a textarea and formatting is layer-wide only.
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import type { Editor } from '@tiptap/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({ SearchableSelect: () => <div data-testid="select" /> }));

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const OWNER_TEXT = '{{product.code}}\n{{product.price_tag_description}}\nLP: {{product.list_price}}';

function layer(text: string, over: Partial<TagLayer> = {}): TagLayer {
  return {
    id: 't1',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 12,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'text',
      text,
      fontFamily: 'DM Sans',
      fontSize: 12,
      fontWeight: 400,
      color: '#000000',
      align: 'left',
      lineHeight: 1.2,
      letterSpacing: 0,
    },
    ...over,
  } as TagLayer;
}

async function mount(l: TagLayer) {
  const onUpdate = vi.fn();
  const onUpdateProps = vi.fn();
  let editor: Editor | null = null;
  const utils = render(
    <InspectorPanel
      layer={l}
      onUpdate={onUpdate}
      onUpdateProps={onUpdateProps}
      resolvedText={null}
      onInsertField={vi.fn()}
      onContentEditorReady={(e: Editor | null) => {
        editor = e;
      }}
    />,
  );
  await waitFor(() => expect(editor).not.toBeNull());
  return { ...utils, onUpdate, onUpdateProps, editor: editor! as Editor };
}

describe('Inspector rich Content box', () => {
  it('is the rich editor with the inline toolbar, not a textarea', async () => {
    const { container } = await mount(layer(OWNER_TEXT));
    expect(container.querySelector('textarea')).toBeNull();
    for (const name of ['Bold selection', 'Italic selection', 'Underline selection', 'Strikethrough selection', 'Selection colour']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument();
    }
    expect(screen.queryByRole('button', { name: 'Heading 1' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Insert field/ })).toBeInTheDocument();
  });

  it('shows the plain content as one paragraph per line with tokens as atoms', async () => {
    const { container } = await mount(layer(OWNER_TEXT));
    const paragraphs = Array.from(container.querySelectorAll('.ProseMirror p')).map((p) => p.textContent);
    expect(paragraphs).toEqual(OWNER_TEXT.split('\n'));
    expect(container.querySelectorAll('.ProseMirror [data-merge-field]')).toHaveLength(3);
  });

  it('bolding only the first line writes rich HTML for that run alone', async () => {
    const { editor, onUpdateProps } = await mount(layer(OWNER_TEXT));
    act(() => {
      // The first paragraph holds the code token alone: positions 1..2.
      editor.chain().setTextSelection({ from: 1, to: 2 }).toggleBold().run();
    });
    const [id, props] = onUpdateProps.mock.calls.at(-1)!;
    expect(id).toBe('t1');
    expect(props.text).toBe(
      '<p><strong>{{product.code}}</strong></p><p>{{product.price_tag_description}}</p><p>LP: {{product.list_price}}</p>',
    );
    // Layer-level defaults untouched.
    expect(props.fontWeight).toBe(400);
  });

  it('an unformatted edit keeps the plain text format', async () => {
    const { editor, onUpdateProps } = await mount(layer('Hello'));
    act(() => {
      editor.commands.setTextSelection(6);
      editor.commands.insertContent('!');
    });
    expect(onUpdateProps.mock.calls.at(-1)![1].text).toBe('Hello!');
  });

  it('a rich layer opens with its formatting', async () => {
    const { container } = await mount(layer('<p><strong>{{product.code}}</strong></p><p>x</p>'));
    expect(container.querySelector('.ProseMirror strong [data-merge-field="product.code"]')).not.toBeNull();
  });

  it('a slot-bound layer writes its formatted content to text_override', async () => {
    const { editor, onUpdate } = await mount(
      layer('', { slot_binding: 'code', text_override: '{{product.code}}' }),
    );
    act(() => {
      editor.chain().selectAll().toggleBold().run();
    });
    expect(onUpdate.mock.calls.at(-1)).toEqual(['t1', { text_override: '<p><strong>{{product.code}}</strong></p>' }]);
  });

  it('a description-bound layer keeps the read-only plain box (R8)', async () => {
    const { container } = render(
      <InspectorPanel
        layer={layer('', { slot_binding: 'price_tag_description' })}
        onUpdate={vi.fn()}
        onUpdateProps={vi.fn()}
        resolvedText="<p><strong>A</strong></p>"
      />,
    );
    const box = container.querySelector('textarea') as HTMLTextAreaElement;
    expect(box.readOnly).toBe(true);
    expect(box.value).toBe('A');
  });
});
