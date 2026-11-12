/**
 * DESIGNER-RICH-TEXT: the shared editor's two opt-in props for the tag designer's Content box.
 *  - `toolbar="inline"`: bold, italic, underline, strike and text colour only.
 *  - `mergeFields`: a `{{path}}` token is ONE atomic node. A mark covers it whole and never splits
 *    it; the emitted HTML carries the token as plain `{{path}}` text.
 * Existing callers (no props) keep the full toolbar and plain text handling.
 *
 * Written test-FIRST: neither prop exists yet.
 */
import '@/test-utils/prosemirrorGeometry';
import * as React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import type { Editor } from '@tiptap/react';
import { describe, expect, it, vi } from 'vitest';

import { RichTextEditor, insertMergeFieldText } from '@/components/ui/rich-text-editor';
import { contentFromEditorHtml } from '@/lib/dealer-kit/layer-content';
import { toEditorHtml } from '@/lib/dealer-kit/rich-text';

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
  it('shows exactly bold, italic, underline, strike and colour, named for the selection', async () => {
    await mount('<p>x</p>', { toolbar: 'inline' });
    for (const name of ['Bold selection', 'Italic selection', 'Underline selection', 'Strikethrough selection', 'Selection colour']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument();
    }
    for (const name of ['Heading 1', 'Bullet list', 'Highlight', 'Add link', 'Inline code', 'Align left', 'Bold']) {
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
      editor.chain().focus().setTextSelection(7).run();
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

  it('mounting emits no change', async () => {
    const { onChange } = await mount('<p>{{product.code}}</p>', { mergeFields: true });
    await new Promise((r) => setTimeout(r, 20));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('typing a quote mid-text keeps the caret when the value comes back the Inspector way', async () => {
    // The Inspector stores `contentFromEditorHtml(html)` and hands back `toEditorHtml(stored)`,
    // which writes `"` as `&quot;`: only a comparison of one serialisation keeps that from
    // resetting the editor (and its caret) on every keystroke.
    let editor: Editor | null = null;
    function Host() {
      const [stored, setStored] = React.useState('ab');
      return (
        <RichTextEditor
          mergeFields
          value={toEditorHtml(stored)}
          onChange={(html) => setStored(contentFromEditorHtml(html))}
          onEditorReady={(e) => {
            editor = e;
          }}
        />
      );
    }
    render(<Host />);
    await waitFor(() => expect(editor).not.toBeNull());
    act(() => {
      editor!.chain().focus().setTextSelection(2).insertContent('"').run();
    });
    expect(editor!.state.selection.from).toBe(3);
  });

  it('a mergeFields editor has no hard break: Shift+Enter cannot make a line the plain format cannot hold', async () => {
    const { editor } = await mount('<p>abc</p>', { mergeFields: true });
    expect(editor.schema.nodes.hardBreak).toBeUndefined();
  });
});

describe('toolbar="inline" holds inline formatting only', () => {
  it.each(['heading', 'bulletList', 'orderedList', 'blockquote', 'codeBlock', 'horizontalRule'])(
    'has no %s node (no shortcut, input rule or paste can make one)',
    async (name) => {
      const { editor } = await mount('<p>x</p>', { toolbar: 'inline', mergeFields: true });
      expect(editor.schema.nodes[name]).toBeUndefined();
    },
  );

  it('has no inline code mark', async () => {
    const { editor } = await mount('<p>x</p>', { toolbar: 'inline', mergeFields: true });
    expect(editor.schema.marks.code).toBeUndefined();
  });

  it('pasted list / heading HTML lands as paragraphs', async () => {
    const { editor, html } = await mount('<p>x</p>', { toolbar: 'inline', mergeFields: true });
    act(() => {
      editor.commands.setContent('<h1>T</h1><ul><li><p>a</p></li></ul>', { emitUpdate: true });
    });
    expect(html()).not.toMatch(/<(h1|ul|li|pre|hr)/);
  });
});

describe('merge-field edge cases', () => {
  it('{{ }} with an empty path stays text', async () => {
    const { editor } = await mount('<p>{{ }}</p>', { mergeFields: true });
    expect(tokenNodes(editor)).toEqual([]);
  });

  it('Insert field into a never-focused editor lands at the end', async () => {
    const { editor, html } = await mount('<p>Price</p>', { mergeFields: true });
    act(() => {
      insertMergeFieldText(editor, '{{product.list_price}}');
    });
    expect(html()).toBe('<p>Price{{product.list_price}}</p>');
  });
});

// Owner hand test, 6 Nov (FAIL 2): a selected token chip showed no highlight, so he could not
// tell whether it was selected. A chip inside the selection carries a visible selected class.
describe('a selected token chip shows that it is selected', () => {
  const chip = (container: HTMLElement, path: string) =>
    container.querySelector<HTMLElement>(`.ProseMirror [data-merge-field="${path}"]`)!;

  it('a text selection across a chip marks it selected', async () => {
    const { container, editor } = await mount('<p>Code {{product.code}} end</p>', { mergeFields: true });
    act(() => {
      editor.chain().setTextSelection({ from: 2, to: 8 }).run();
    });
    expect(chip(container, 'product.code').classList).toContain('merge-field-selected');
  });

  it('a click selection of the chip itself marks it selected', async () => {
    const { container, editor } = await mount('<p>Code {{product.code}} end</p>', { mergeFields: true });
    act(() => {
      editor.chain().setNodeSelection(6).run();
    });
    expect(chip(container, 'product.code').classList).toContain('merge-field-selected');
  });

  it('a chip outside the selection, or a collapsed caret, is not marked', async () => {
    const { container, editor } = await mount('<p>{{product.code}} and {{spec.width}}</p>', {
      mergeFields: true,
    });
    act(() => {
      editor.chain().setTextSelection({ from: 2, to: 6 }).run();
    });
    expect(chip(container, 'spec.width').classList).not.toContain('merge-field-selected');
    act(() => {
      editor.chain().setTextSelection(2).run();
    });
    expect(chip(container, 'product.code').classList).not.toContain('merge-field-selected');
  });
});

describe('toolbar="none" (the canvas in-place editor)', () => {
  it('renders no toolbar and no box chrome, only the editable text', async () => {
    const { container } = await mount('<p>x</p>', { toolbar: 'none', mergeFields: true });
    expect(screen.queryByRole('button')).toBeNull();
    const dom = container.querySelector<HTMLElement>('.ProseMirror')!;
    expect(dom.className).not.toMatch(/\bprose\b/);
  });

  it('holds inline formatting only, like the inline toolbar', async () => {
    const { editor } = await mount('<p>x</p>', { toolbar: 'none', mergeFields: true });
    expect(editor.schema.nodes.heading).toBeUndefined();
    expect(editor.schema.nodes.bulletList).toBeUndefined();
    expect(editor.schema.marks.bold).toBeDefined();
  });
});

describe('mergeFieldLabel (COMBO-SETTINGS-UX: chips named by the part)', () => {
  it('shows a chip by its readable name while the value keeps the plain token', async () => {
    const label = (path: string) => (path === 'part.main.code' ? 'CABINET - SRTBF11829: code' : null);
    const { container, editor, html } = await mount('<p>A {{part.main.code}} {{combo.name}}</p>', {
      mergeFields: true,
      mergeFieldLabel: label,
    });
    const chips = [...container.querySelectorAll('[data-merge-field]')].map((el) => el.textContent);
    expect(chips).toEqual(['CABINET - SRTBF11829: code', '{{combo.name}}']);
    act(() => {
      insertMergeFieldText(editor, '!');
    });
    expect(html()).toContain('{{part.main.code}}');
    expect(html()).not.toContain('CABINET - SRTBF11829');
  });
});
