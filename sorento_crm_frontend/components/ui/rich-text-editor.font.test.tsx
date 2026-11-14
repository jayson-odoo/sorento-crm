/**
 * PRICETAG-DESIGNER-FEEDBACK B1, AC-1.4: font per word in the shared editor.
 *
 * With `fontOptions`, the inline and full toolbars show a font picker (the shared clearable
 * `SearchableSelect`, labelled "Font") and a size field in pt (labelled "Font size"). Picking
 * "Montserrat" and 14 wraps exactly the selection in
 * `<span style="font-family: Montserrat; font-size: 14pt">`; clearing removes the mark. Without
 * `fontOptions` the toolbar is unchanged. Written test-FIRST.
 *
 * `SearchableSelect` is swapped for a native select (as other suites do) so the pick and the
 * clear (`onChange('')`) are driven without its popover. The text is selected through the editor
 * handed out by `onEditorReady` (jsdom has no selection gestures).
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { Editor } from '@tiptap/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    'aria-label'?: string;
    placeholder?: string;
    value?: string | null;
    onChange?: (v: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select
      aria-label={props['aria-label'] ?? (typeof props.placeholder === 'string' ? props.placeholder : '')}
      value={props.value ?? ''}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
      <option value="">-</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { RichTextEditor } from '@/components/ui/rich-text-editor';

const FONTS = [
  { value: 'Montserrat', label: 'Montserrat' },
  { value: 'Jost', label: 'Jost' },
];

type Toolbar = 'full' | 'inline';

async function mount(
  initial: string,
  { toolbar = 'full', fonts = FONTS }: { toolbar?: Toolbar; fonts?: typeof FONTS | null } = {},
) {
  const onChange = vi.fn();
  let editor: Editor | null = null;
  const extra = fonts ? { fontOptions: fonts } : {};
  render(
    <RichTextEditor
      value={initial}
      onChange={onChange}
      toolbar={toolbar}
      onEditorReady={(e) => {
        editor = e;
      }}
      {...(extra as Record<string, unknown>)}
    />,
  );
  await waitFor(() => expect(editor).not.toBeNull());
  const html = () => String(onChange.mock.calls.at(-1)?.[0] ?? (editor as Editor | null)?.getHTML() ?? '');
  return { onChange, html, editor: editor! as Editor };
}

/** "world" in `<p>hello world</p>`: the paragraph opens at 0, its text starts at 1. */
function selectWorld(editor: Editor) {
  act(() => {
    editor.commands.setTextSelection({ from: 7, to: 12 });
  });
}

function setSize(value: string) {
  const input = screen.getByLabelText('Font size');
  fireEvent.change(input, { target: { value } });
  fireEvent.keyDown(input, { key: 'Enter' });
  fireEvent.blur(input);
}

describe.each<Toolbar>(['full', 'inline'])('RichTextEditor font per word, %s toolbar (AC-1.4)', (toolbar) => {
  it('shows a font picker and a size field when fontOptions is given', async () => {
    await mount('<p>hello world</p>', { toolbar });
    const picker = screen.getByLabelText('Font');
    expect(picker).toBeInTheDocument();
    expect(Array.from((picker as HTMLSelectElement).options).map((o) => o.textContent)).toEqual(
      expect.arrayContaining(['Montserrat', 'Jost']),
    );
    expect(screen.getByLabelText('Font size')).toBeInTheDocument();
  });

  it('wraps exactly the selection in the picked font and size', async () => {
    const { html, editor } = await mount('<p>hello world</p>', { toolbar });
    selectWorld(editor);
    fireEvent.change(screen.getByLabelText('Font'), { target: { value: 'Montserrat' } });
    setSize('14');

    await waitFor(() =>
      expect(html()).toContain(
        '<p>hello <span style="font-family: Montserrat; font-size: 14pt">world</span></p>',
      ),
    );
  });

  it('keeps an existing font span when the value is loaded', async () => {
    const value = '<p>hello <span style="font-family: Montserrat; font-size: 14pt">world</span></p>';
    const { editor } = await mount(value, { toolbar });
    // TipTap serialises a trailing ';' in the style attribute; it is allowed, nothing else changes.
    expect(editor.getHTML()).toMatch(/<span style="font-family: Montserrat; font-size: 14pt;?">world<\/span>/);
  });

  it('clearing the font and the size removes the mark', async () => {
    const { html, editor } = await mount(
      '<p>hello <span style="font-family: Montserrat; font-size: 14pt">world</span></p>',
      { toolbar },
    );
    selectWorld(editor);
    fireEvent.change(screen.getByLabelText('Font'), { target: { value: '' } });
    await waitFor(() => expect(html()).not.toContain('font-family'));
    expect(html()).toContain('font-size: 14pt');

    selectWorld(editor);
    setSize('');
    await waitFor(() => expect(html()).not.toContain('font-size'));
    expect(html()).not.toContain('<span');
    expect(html()).toContain('hello world');
  });
});

describe('RichTextEditor without fontOptions (AC-1.4)', () => {
  it.each<Toolbar>(['full', 'inline'])('%s toolbar is unchanged: no font picker, no size field', async (toolbar) => {
    await mount('<p>hello world</p>', { toolbar, fonts: null });
    expect(screen.queryByLabelText('Font')).toBeNull();
    expect(screen.queryByLabelText('Font size')).toBeNull();
  });
});
