import '@/test-utils/prosemirrorGeometry';
/**
 * DESIGNER-RICH-TEXT review round 2: the rich in-place editor commits when focus leaves it (a
 * click on the Inspector, the toolbar, empty canvas, the same layer staying selected), and moving
 * focus WITHIN it is not leaving it.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { Editor } from '@tiptap/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { defaultTextProps } from '@/lib/dealer-kit/tag-template-types';
import { InlineTextEditor } from './InlineTextEditor';

const layer = {
  id: 'l1',
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
  props: { ...defaultTextProps(), text: 'Hello' },
} as TagLayer;

async function open(onCommit = vi.fn(), onCancel = vi.fn()) {
  render(
    <InlineTextEditor
      rich
      layer={layer}
      value="Hello"
      scale={3}
      originX={0}
      originY={0}
      onCommit={onCommit}
      onCancel={onCancel}
    />,
  );
  const host = screen.getByTestId('inline-rich-editor');
  const dom = await waitFor(() => {
    const el = host.querySelector<HTMLElement>('.ProseMirror');
    expect(el).not.toBeNull();
    return el!;
  });
  const editor = (dom as unknown as { editor: Editor }).editor;
  return { host, dom, editor, onCommit, onCancel };
}

describe('rich in-place editor: leaving by blur', () => {
  it('focus moving OUTSIDE the editor commits the edit', async () => {
    const { dom, editor, onCommit } = await open();
    editor.chain().focus('end').insertContent('!').run();
    const outside = document.createElement('button');
    document.body.appendChild(outside);
    fireEvent.blur(dom, { relatedTarget: outside });
    expect(onCommit).toHaveBeenCalledWith('Hello!');
  });

  it('focus moving WITHIN the editor does not commit', async () => {
    const { host, dom, editor, onCommit, onCancel } = await open();
    editor.chain().focus('end').insertContent('!').run();
    fireEvent.blur(dom, { relatedTarget: host.querySelector('span') });
    expect(onCommit).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('leaving with no edit cancels (B2)', async () => {
    const { dom, onCommit, onCancel } = await open();
    fireEvent.blur(dom, { relatedTarget: document.body });
    expect(onCommit).not.toHaveBeenCalled();
    expect(onCancel).toHaveBeenCalled();
  });
});
