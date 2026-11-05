/**
 * PRICETAG-COMBO-FORMAT fix round 1, R9: colour and alignment come only from the toolbar. Pasted
 * HTML loses its `style` attributes; and the output normaliser works on parsed elements, so text
 * that merely looks like a style attribute is never rewritten.
 *
 * Written test-FIRST: pasted `color: white; text-align: center` is kept today (white text on a
 * white tag).
 */
import { act, render, waitFor } from '@testing-library/react';
import type { Editor } from '@tiptap/react';
import { describe, expect, it, vi } from 'vitest';

import { RichTextEditor } from '@/components/ui/rich-text-editor';

// jsdom has no ClipboardEvent; ProseMirror's `pasteHTML` builds one.
if (typeof (globalThis as { ClipboardEvent?: unknown }).ClipboardEvent === 'undefined') {
  class ClipboardEventStub extends Event {
    clipboardData: DataTransfer | null;
    constructor(type: string, init: { clipboardData?: DataTransfer | null } = {}) {
      super(type, { bubbles: true, cancelable: true });
      this.clipboardData = init.clipboardData ?? null;
    }
  }
  (globalThis as unknown as { ClipboardEvent: unknown }).ClipboardEvent = ClipboardEventStub;
}

async function mount(initial = '<p>start</p>') {
  const onChange = vi.fn();
  let editor: Editor | null = null;
  render(
    <RichTextEditor
      value={initial}
      onChange={onChange}
      onEditorReady={(e) => {
        editor = e;
      }}
    />,
  );
  await waitFor(() => expect(editor).not.toBeNull());
  const html = () => String(onChange.mock.calls.at(-1)?.[0] ?? '');
  return { editor: editor! as Editor, onChange, html };
}

describe('pasted HTML keeps no style (R9)', () => {
  it('R9: pasted colour and alignment are dropped, the text stays', async () => {
    const { editor, html } = await mount();
    act(() => {
      editor.commands.focus('end');
      editor.view.pasteHTML(
        '<p style="color: white; text-align: center">pasted <span style="color: white">words</span></p>',
      );
    });
    await waitFor(() => expect(html()).toContain('pasted'));
    expect(html()).toContain('words');
    expect(html()).not.toMatch(/color:\s*white/i);
    expect(html()).not.toContain('text-align');
    expect(html()).not.toContain('style=');
  });

  it('R9: pasted background colour and font size are dropped too', async () => {
    const { editor, html } = await mount();
    act(() => {
      editor.commands.focus('end');
      editor.view.pasteHTML('<p><mark style="background-color: yellow; font-size: 40px">loud</mark></p>');
    });
    await waitFor(() => expect(html()).toContain('loud'));
    expect(html()).not.toContain('font-size');
    expect(html()).not.toContain('yellow');
  });

  it('R9: a toolbar colour still works after the change', async () => {
    const { editor, html } = await mount('<p>hello</p>');
    act(() => {
      editor.commands.selectAll();
      editor.chain().focus().setColor('#6b7280').run();
    });
    await waitFor(() => expect(html().toLowerCase()).toContain('color: #6b7280'));
  });
});

describe('the normaliser never rewrites text (R9)', () => {
  it('R9: typed text that looks like a style attribute survives unchanged', async () => {
    const { editor, html } = await mount('<p></p>');
    act(() => {
      editor.commands.focus('end');
      editor.commands.insertContent({ type: 'text', text: 'style="a;b" and style="color: red;"' });
    });
    await waitFor(() => expect(html()).toContain('style='));
    expect(html()).toBe('<p>style="a;b" and style="color: red;"</p>');
  });
});
