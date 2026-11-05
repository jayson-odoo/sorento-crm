/**
 * PRICETAG-COMBO-FORMAT S1 (AC-1, AC-2): the shared editor gains Text colour, Highlight, Underline
 * and Align left / centre / right. Written test-FIRST: none of these buttons exist yet.
 *
 * The text is selected through the editor handed out by `onEditorReady` (jsdom has no real
 * selection gestures). The colour popover is the shared `ColorPicker`; a colour is committed
 * through its "Hex colour" box (Enter), the same way its own suite does.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { Editor } from '@tiptap/react';
import { describe, expect, it, vi } from 'vitest';

import { RichTextEditor } from '@/components/ui/rich-text-editor';

async function mount(initial = '<p>hello</p>') {
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
  act(() => {
    editor!.commands.selectAll();
  });
  const html = () => String(onChange.mock.calls.at(-1)?.[0] ?? '').toLowerCase();
  return { onChange, html, editor: editor! as Editor };
}

const button = (name: string) => screen.getByRole('button', { name });

describe('RichTextEditor toolbar (AC-1)', () => {
  it('AC-1: has the new buttons beside the existing ones', async () => {
    await mount();
    for (const name of [
      'Text colour',
      'Highlight',
      'Underline',
      'Align left',
      'Align centre',
      'Align right',
      // today's buttons stay
      'Bold',
      'Italic',
      'Strikethrough',
      'Inline code',
      'Heading 1',
      'Heading 2',
      'Heading 3',
      'Bullet list',
      'Ordered list',
      'Blockquote',
      'Add link',
      'Undo',
      'Redo',
    ]) {
      expect(button(name), name).toBeInTheDocument();
    }
  });
});

describe('RichTextEditor formatting (AC-2)', () => {
  it('AC-2: a picked text colour is emitted as <span style="color: #6b7280">', async () => {
    const { html } = await mount();
    fireEvent.click(button('Text colour'));
    const hex = await screen.findByLabelText('Hex colour');
    fireEvent.change(hex, { target: { value: '#6B7280' } });
    fireEvent.keyDown(hex, { key: 'Enter' });

    await waitFor(() => expect(html()).toContain('<span style="color: #6b7280">'));
  });

  it('AC-2: "Remove colour" takes the span away', async () => {
    const { html } = await mount('<p><span style="color: #6b7280">hello</span></p>');
    fireEvent.click(button('Text colour'));
    fireEvent.click(await screen.findByRole('button', { name: 'Remove colour' }));

    await waitFor(() => expect(html()).not.toContain('color'));
    expect(html()).toContain('hello');
  });

  it('AC-2: Highlight emits background-color', async () => {
    const { html } = await mount();
    fireEvent.click(button('Highlight'));
    const hex = await screen.findByLabelText('Hex colour');
    fireEvent.change(hex, { target: { value: '#FDE68A' } });
    fireEvent.keyDown(hex, { key: 'Enter' });

    await waitFor(() => expect(html()).toContain('background-color: #fde68a'));
  });

  it('AC-2: Align centre puts text-align: center on the paragraph', async () => {
    const { html } = await mount();
    fireEvent.click(button('Align centre'));

    await waitFor(() => expect(html()).toContain('<p style="text-align: center">'));
  });

  it('AC-2: Underline toggles <u>', async () => {
    const { html } = await mount();
    fireEvent.click(button('Underline'));
    await waitFor(() => expect(html()).toContain('<u>hello</u>'));

    act(() => {
      // keep the selection, as a user would
    });
    fireEvent.click(button('Underline'));
    await waitFor(() => expect(html()).not.toContain('<u>'));
  });
});

describe('RichTextEditor leaves existing screens alone (AC-4)', () => {
  it('AC-4: bold, italic and lists emit the markup they did before', async () => {
    const { html } = await mount();
    fireEvent.click(button('Bold'));
    await waitFor(() => expect(html()).toBe('<p><strong>hello</strong></p>'));
    fireEvent.click(button('Bullet list'));
    await waitFor(() => expect(html()).toContain('<ul><li><p><strong>hello</strong></p></li></ul>'));
  });

  it('AC-4: no new markup without a new button press', async () => {
    const { onChange, editor } = await mount('<p>a</p>');
    act(() => {
      editor.commands.focus('end');
      editor.commands.insertContent('b');
    });
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    expect(String(onChange.mock.calls.at(-1)?.[0])).toBe('<p>ab</p>');
  });
});
