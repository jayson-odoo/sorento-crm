/**
 * The inline editor's commit paths (S2, D5, AC-S2-1/2). Positioning maths is
 * exercised implicitly (the style asserted below), the interesting behaviour
 * is WHEN it commits: Esc and Cmd/Ctrl+Enter commit and stop, blur commits
 * once, plain Enter is left to the textarea's own default and never commits.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InlineTextEditor } from './InlineTextEditor';

function textLayer(overrides: Record<string, unknown> = {}): TagLayer {
  return {
    id: 'l1',
    type: 'text',
    x_mm: 10,
    y_mm: 5,
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
      text: 'Hello',
      fontFamily: 'DM Sans',
      fontSize: 12,
      fontWeight: 400,
      color: '#000000',
      align: 'left',
      lineHeight: 1.2,
      letterSpacing: 0,
    },
    ...overrides,
  } as TagLayer;
}

describe('InlineTextEditor', () => {
  it('opens focused with the caret at the end and the seed value (AC-S2-1)', () => {
    render(
      <InlineTextEditor
        layer={textLayer()}
        value="Hello"
        scale={4}
        originX={0}
        originY={0}
        onCommit={vi.fn()}
      />,
    );
    const el = screen.getByTestId('inline-text-editor') as HTMLTextAreaElement;
    expect(el).toHaveFocus();
    expect(el.selectionStart).toBe('Hello'.length);
    expect(el.selectionEnd).toBe('Hello'.length);
  });

  it('positions over the node at x_mm/y_mm * scale, offset by origin', () => {
    render(
      <InlineTextEditor
        layer={textLayer({ x_mm: 10, y_mm: 5, width_mm: 40, height_mm: 12 })}
        value="Hello"
        scale={4}
        originX={20}
        originY={30}
        onCommit={vi.fn()}
      />,
    );
    const el = screen.getByTestId('inline-text-editor');
    expect(el).toHaveStyle({ left: '60px', top: '50px', width: '160px', height: '48px' });
  });

  it('commits on Escape and does not commit twice on the blur that follows', () => {
    const onCommit = vi.fn();
    render(
      <InlineTextEditor
        layer={textLayer()}
        value="Hello"
        scale={4}
        originX={0}
        originY={0}
        onCommit={onCommit}
      />,
    );
    const el = screen.getByTestId('inline-text-editor');
    fireEvent.change(el, { target: { value: 'Hello there' } });
    fireEvent.keyDown(el, { key: 'Escape' });
    fireEvent.blur(el);
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith('Hello there');
  });

  it('commits on Cmd/Ctrl+Enter', () => {
    const onCommit = vi.fn();
    render(
      <InlineTextEditor
        layer={textLayer()}
        value="Hello"
        scale={4}
        originX={0}
        originY={0}
        onCommit={onCommit}
      />,
    );
    const el = screen.getByTestId('inline-text-editor');
    fireEvent.change(el, { target: { value: 'Hello there' } });
    fireEvent.keyDown(el, { key: 'Enter', metaKey: true });
    expect(onCommit).toHaveBeenCalledWith('Hello there');
  });

  it('commits once on blur when neither shortcut fired', () => {
    const onCommit = vi.fn();
    render(
      <InlineTextEditor
        layer={textLayer()}
        value="Hello"
        scale={4}
        originX={0}
        originY={0}
        onCommit={onCommit}
      />,
    );
    const el = screen.getByTestId('inline-text-editor');
    fireEvent.change(el, { target: { value: 'Edited' } });
    fireEvent.blur(el);
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith('Edited');
  });

  it('leaves a plain Enter to insert a newline rather than committing', () => {
    const onCommit = vi.fn();
    render(
      <InlineTextEditor
        layer={textLayer()}
        value="Hello"
        scale={4}
        originX={0}
        originY={0}
        onCommit={onCommit}
      />,
    );
    const el = screen.getByTestId('inline-text-editor');
    fireEvent.keyDown(el, { key: 'Enter' });
    expect(onCommit).not.toHaveBeenCalled();
  });
});
