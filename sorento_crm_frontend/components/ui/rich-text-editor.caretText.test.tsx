/**
 * PRICETAG-DESIGNER-FEEDBACK AC-4.2: `textAroundMergeFieldCaret` reads the plain text on each side
 * of the rich editor's caret (blocks joined by "\n", each field as its `{{path}}`), which the
 * Insert field dialog shows around its insert point. Real RichTextEditor with `mergeFields`, as
 * the Inspector's Content box mounts it.
 */
import '@/test-utils/prosemirrorGeometry';
import { act, render, waitFor } from '@testing-library/react';
import type { Editor } from '@tiptap/react';
import { describe, expect, it, vi } from 'vitest';

import { RichTextEditor, textAroundMergeFieldCaret } from '@/components/ui/rich-text-editor';

const CONTENT = '<p>{{combo.description}}</p><p><strong>LP: RM {{product.list_price}}</strong></p>';
const FULL = '{{combo.description}}\nLP: RM {{product.list_price}}';

async function mount(): Promise<Editor> {
  let editor: Editor | null = null;
  render(
    <RichTextEditor
      value={CONTENT}
      onChange={vi.fn()}
      mergeFields
      onEditorReady={(e) => {
        editor = e;
      }}
    />,
  );
  await waitFor(() => expect(editor).not.toBeNull());
  return editor!;
}

/** The document position right after `needle` inside a text node. */
function positionAfter(editor: Editor, needle: string): number {
  let at = -1;
  editor.state.doc.descendants((node, pos) => {
    if (at < 0 && node.isText && node.text?.includes(needle)) {
      at = pos + node.text.indexOf(needle) + needle.length;
    }
  });
  expect(at, `found "${needle}"`).toBeGreaterThan(0);
  return at;
}

describe('textAroundMergeFieldCaret (AC-4.2)', () => {
  it('caret after "RM ": before ends "LP: RM ", after starts with the price token', async () => {
    const editor = await mount();
    const caret = positionAfter(editor, 'LP: RM ');
    act(() => {
      editor.chain().focus().setTextSelection(caret).run();
    });
    const { before, after } = textAroundMergeFieldCaret(editor);
    expect(before).toBe('{{combo.description}}\nLP: RM ');
    expect(before.endsWith('LP: RM ')).toBe(true);
    expect(after).toBe('{{product.list_price}}');
    expect(after.startsWith('{{product.list_price}}')).toBe(true);
  });

  it('an editor never focused: everything is before, nothing after (fields go at the end)', async () => {
    const editor = await mount();
    expect(textAroundMergeFieldCaret(editor)).toEqual({ before: FULL, after: '' });
  });

  it('a selected range is left out of both sides (a pick replaces it)', async () => {
    const editor = await mount();
    const to = positionAfter(editor, 'LP: RM ');
    const from = to - 'RM '.length;
    act(() => {
      editor.chain().focus().setTextSelection({ from, to }).run();
    });
    const { before, after } = textAroundMergeFieldCaret(editor);
    expect(before).toBe('{{combo.description}}\nLP: ');
    expect(after).toBe('{{product.list_price}}');
    expect(before + after).not.toContain('RM');
  });
});
