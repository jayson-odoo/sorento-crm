/**
 * PRICETAG-DESIGNER-FEEDBACK AC-2.5: the shared RichTextEditor keeps leading and repeated spaces
 * when content is loaded (owner, 14 Nov: after a refresh the indent of "   L580xW450xH450mm" was
 * gone in the editor, and the next save stored it stripped).
 *
 * Written test-FIRST. Spaces may come back as plain spaces or as &nbsp; (U+00A0); both count.
 */
import '@/test-utils/prosemirrorGeometry';
import { render, waitFor } from '@testing-library/react';
import type { Editor } from '@tiptap/react';
import { describe, expect, it, vi } from 'vitest';

import { RichTextEditor } from '@/components/ui/rich-text-editor';

async function mount(initial: string, extra: Record<string, unknown> = {}) {
  const onChange = vi.fn();
  let editor: Editor | null = null;
  render(
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
  return { editor: editor! as Editor, onChange };
}

/** Editor HTML with &nbsp; / U+00A0 read as a plain space. */
const spaced = (html: string) => html.replace(/&nbsp;|&#160;| /g, ' ');

for (const [label, extra] of [
  ['default editor', {}],
  ['description editor (mergeFields)', { mergeFields: true }],
] as const) {
  describe(`AC-2.5: ${label} keeps spaces on load`, () => {
    it('AC-2.5: <p>   L580</p> loads with its 3 leading spaces', async () => {
      const { editor } = await mount('<p>   L580</p>', extra);
      expect(spaced(editor.getHTML())).toContain('<p>   L580</p>');
    });

    it('AC-2.5: repeated spaces between words are kept on load', async () => {
      const { editor } = await mount('<p>Basin   size</p>', extra);
      expect(spaced(editor.getHTML())).toContain('Basin   size');
    });

    it('AC-2.5: the indent survives a value handed in after mount (load from API)', async () => {
      const onChange = vi.fn();
      let editor: Editor | null = null;
      const view = render(
        <RichTextEditor value="" onChange={onChange} onEditorReady={(e) => (editor = e)} {...extra} />,
      );
      await waitFor(() => expect(editor).not.toBeNull());
      view.rerender(
        <RichTextEditor
          value="<p>Basin size:</p><p>   L580xW450xH450mm</p>"
          onChange={onChange}
          onEditorReady={(e) => (editor = e)}
          {...extra}
        />,
      );
      await waitFor(() => expect(spaced(editor!.getHTML())).toContain('<p>   L580xW450xH450mm</p>'), {
        timeout: 1000,
      });
      for (const call of onChange.mock.calls) {
        expect(spaced(String(call[0]))).toContain('   L580');
      }
    });

    it('AC-2.5: an untouched editor never emits a change that strips the spaces', async () => {
      const { onChange } = await mount('<p>   L580</p>', extra);
      // Give any mount-time emission a chance to land.
      await new Promise((resolve) => setTimeout(resolve, 20));
      for (const call of onChange.mock.calls) {
        expect(spaced(String(call[0]))).toContain('<p>   L580</p>');
      }
    });
  });
}
