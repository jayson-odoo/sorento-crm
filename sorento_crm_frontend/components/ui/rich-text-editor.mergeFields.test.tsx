/**
 * DESIGNER-RICH-TEXT: the shared editor's two opt-in props for the tag designer's Content box.
 *  - `toolbar="inline"`: bold, italic, underline, strike and text colour only.
 *  - `mergeFields`: a `{{path}}` token is ONE atomic node. A mark covers it whole and never splits
 *    it; the emitted HTML carries the token as plain `{{path}}` text.
 * Existing callers (no props) keep the full toolbar and plain text handling.
 *
 * Written test-FIRST: neither prop exists yet.
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import type { Editor } from '@tiptap/react';
import { describe, expect, it, vi } from 'vitest';

import { RichTextEditor, insertMergeFieldText } from '@/components/ui/rich-text-editor';

async function mount(initial: string, extra: Record<string, unknown> = {}) {
  const onChange = vi.fn();
  let editor: Editor | null = null;
  const utils = render(
    <RichTextEditor
      value={initial}
      onChange={onChange}
      onEditorReady={(e) => {
        editor = e;
      }}
      {...extra}
    />,
  );
  await waitFor(() => expect(editor).not.toBeNull());
  const html = () => String(onChange.mock.calls.at(-1)?.[0] ?? '');
  return { ...utils, onChange, html, editor: editor! as Editor };
}

const tokenNodes = (editor: Editor) => {
  const out: Array<{ path: string; marks: string[] }> = [];
  editor.state.doc.descendants((node) => {
    if (node.type.name === 'mergeField') {
      out.push({ path: node.attrs.path, marks: node.marks.map((m) => m.type.name) });
    }
  });
  return out;
};

describe('toolbar="inline"', () => {
  it('shows exactly bold, italic, underline, strike and text colour', async () => {
    await mount('<p>x</p>', { toolbar: 'inline' });
    for (const name of ['Bold', 'Italic', 'Underline', 'Strikethrough', 'Text colour']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument();
    }
    for (const name of ['Heading 1', 'Bullet list', 'Highlight', 'Add link', 'Inline code', 'Align left']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
  });

  it('the default toolbar is unchanged (Heading 1 still there)', async () => {
    await mount('<p>x</p>');
    expect(screen.getByRole('button', { name: 'Heading 1' })).toBeInTheDocument();
  });
});

describe('mergeFields', () => {
  it('loads each {{token}} as one atomic node', async () => {
    const { editor } = await mount('<p>LP: {{product.list_price}}</p><p>{{product.code}}</p>', {
      mergeFields: true,
    });
    expect(tokenNodes(editor).map((t) => t.path)).toEqual(['product.list_price', 'product.code']);
    let atom = false;
    editor.state.doc.descendants((node) => {
      if (node.type.name === 'mergeField') atom = node.isAtom;
    });
    expect(atom).toBe(true);
  });

  it('a selection that starts mid-text and ends after a token bolds the token whole', async () => {
    const { editor, html } = await mount('<p>LP: {{product.list_price}}</p>', { mergeFields: true });
    // "LP: " is positions 1..5, the token node 5..6.
    act(() => {
      editor.chain().setTextSelection({ from: 3, to: 6 }).toggleBold().run();
    });
    expect(html()).toBe('<p>LP<strong>: {{product.list_price}}</strong></p>');
    expect(tokenNodes(editor)).toEqual([{ path: 'product.list_price', marks: ['bold'] }]);
  });

  it('emits tokens as plain {{path}} text, never the editor wrapper', async () => {
    const { editor, html } = await mount('<p>{{product.code}}</p>', { mergeFields: true });
    act(() => {
      editor.chain().selectAll().toggleItalic().run();
    });
    expect(html()).toBe('<p><em>{{product.code}}</em></p>');
    expect(html()).not.toContain('data-merge-field');
  });

  it('insertMergeFieldText puts a token node at the caret', async () => {
    const { editor, html } = await mount('<p>Code: !</p>', { mergeFields: true });
    act(() => {
      editor.commands.setTextSelection(7);
      insertMergeFieldText(editor, '{{product.code}}');
    });
    expect(html()).toBe('<p>Code: {{product.code}}!</p>');
    expect(tokenNodes(editor).map((t) => t.path)).toEqual(['product.code']);
  });

  it('a token typed (inserted as plain text) becomes a node too', async () => {
    const { editor } = await mount('<p>x </p>', { mergeFields: true });
    act(() => {
      editor.commands.setTextSelection(3);
      editor.commands.insertContent('{{spec.width}}');
    });
    expect(tokenNodes(editor).map((t) => t.path)).toEqual(['spec.width']);
  });

  it('without mergeFields a token stays plain text (existing callers)', async () => {
    const { editor } = await mount('<p>{{product.code}}</p>');
    expect(tokenNodes(editor)).toEqual([]);
  });
});
