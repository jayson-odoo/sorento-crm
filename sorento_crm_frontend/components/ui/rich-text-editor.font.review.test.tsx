/**
 * PRICETAG-DESIGNER-FEEDBACK B1 review round (AC-1.4, AC-1.5): the editor only ever holds a font
 * the server would keep.
 *
 * 1. A span whose font is not a plain family name / a pt size loads as bare text, as before B1.
 * 2. A pasted `font:` shorthand brings no font with it (fonts come only from the toolbar).
 *
 * Paste is driven the way rich-text-editor.paste.test.tsx drives it (`editor.view.pasteHTML`).
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

// ProseMirror scrolls the caret into view after a paste, and jsdom lacks the geometry it asks for.
const emptyRects = { length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] };
for (const proto of [Range.prototype, Text.prototype, Element.prototype] as Array<Record<string, unknown>>) {
  if (typeof proto.getClientRects !== 'function') proto.getClientRects = () => emptyRects;
}
if (typeof Range.prototype.getBoundingClientRect !== 'function') {
  Range.prototype.getBoundingClientRect = () => new DOMRect(0, 0, 0, 0);
}

const FONTS = [{ value: 'Montserrat', label: 'Montserrat' }];

async function mount(initial: string, withFonts: boolean) {
  const onChange = vi.fn();
  let editor: Editor | null = null;
  const extra = (withFonts ? { fontOptions: FONTS } : {}) as Record<string, unknown>;
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
  const html = () => String(onChange.mock.calls.at(-1)?.[0] ?? '');
  return { editor: editor! as Editor, html };
}

describe.each([
  ['without fontOptions', false],
  ['with fontOptions', true],
])('RichTextEditor %s: a font the server would drop loads as bare text', (_name, withFonts) => {
  it.each([
    '<p><span style="font-family: Arial, sans-serif">x</span></p>',
    '<p><span style="font-size: 12px">x</span></p>',
  ])('%s loads as <p>x</p>', async (value) => {
    const { editor } = await mount(value, withFonts);
    expect(editor.getHTML()).toBe('<p>x</p>');
  });
});

describe.each([
  ['without fontOptions', false],
  ['with fontOptions', true],
])('RichTextEditor %s: a pasted font shorthand brings no font', (_name, withFonts) => {
  it('pasting <span style="font: 14pt Arial"> keeps the text, drops the font', async () => {
    const { editor, html } = await mount('<p>start</p>', withFonts);
    act(() => {
      editor.commands.focus('end');
      editor.view.pasteHTML('<p><span style="font: 14pt Arial">x</span></p>');
    });
    await waitFor(() => expect(html()).toContain('x'));
    const out = editor.getHTML();
    expect(out).not.toMatch(/font-family/i);
    expect(out).not.toMatch(/font-size/i);
    expect(out).not.toMatch(/font\s*:/i);
    expect(out).not.toContain('<span');
  });
});
