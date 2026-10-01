/**
 * PROMPT-DYNAMIC R5a (owner, 30 Sep 2026: "it needs to stay visualized during edit time,
 * all the time; it should be a variable wired into the prompt; if I want to overwrite I can
 * remove the variable"). Red before the component exists.
 */
import React, { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { PromptChipEditor } from './PromptChipEditor';
import type { RegistryVariableRow } from '../../services/aiPromptsService';

const VARS: RegistryVariableRow[] = [
  { name: 'domains', label: 'Domains', source: 'Chatbot Domains', href: '/system-management/chatbot-domains', count: 15, last_changed: '2026-09-30T09:00:00', rendered: 'master_products | order | sales', used: false },
  { name: 'statuses', label: 'Status words', source: 'Chatbot Status Words', href: '/system-management/chatbot-status-words', count: 8, last_changed: null, rendered: '  - "outstanding" -> orders NOT yet delivered.', used: false },
];
const NAMES = VARS.map((v) => v.name);

let last = '';
function Harness({ initial }: { initial: string }) {
  const [v, setV] = useState(initial);
  last = v;
  return (
    <PromptChipEditor
      value={v}
      onChange={(next) => setV(next)}
      variables={VARS}
      registryNames={NAMES}
    />
  );
}

afterEach(() => cleanup());

function editor() {
  return screen.getByTestId('prompt-chip-editor');
}

describe('PromptChipEditor', () => {
  it('draws each registry variable as a chip with its source and row count, never as raw text', () => {
    render(<Harness initial={'ONE of: {{domains}} | null {{current_date}}'} />);
    const chip = editor().querySelector('[data-chip="domains"]') as HTMLElement;
    expect(chip).not.toBeNull();
    expect(chip.textContent).toContain('Domains');
    expect(chip.textContent).toContain('15 rows');
    expect(chip.getAttribute('contenteditable')).toBe('false');
    expect(editor().textContent).not.toContain('{{domains}}');
    // A token that is not a registry variable stays as text.
    expect(editor().textContent).toContain('{{current_date}}');
    const link = chip.querySelector('a') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('/system-management/chatbot-domains');
  });

  it('expands a chip to show the text the model receives', () => {
    render(<Harness initial={'x {{domains}} y'} />);
    fireEvent.click(screen.getByTestId('chip-toggle-domains'));
    expect(screen.getByTestId('chip-rendered-domains').textContent).toBe('master_products | order | sales');
  });

  it('removing a chip removes the variable, and Undo puts it back', () => {
    render(<Harness initial={'A {{domains}} B'} />);
    fireEvent.click(screen.getByTestId('chip-remove-domains'));
    expect(last).toBe('A  B');
    expect(editor().querySelector('[data-chip="domains"]')).toBeNull();
    fireEvent.click(screen.getByTestId('chip-undo'));
    expect(last).toBe('A {{domains}} B');
    expect(editor().querySelector('[data-chip="domains"]')).not.toBeNull();
  });

  it('typing in the text keeps the chips and serialises back to tokens', () => {
    render(<Harness initial={'A {{domains}} B'} />);
    const textNode = editor().lastChild as Text;
    textNode.textContent = ' B and more';
    fireEvent.input(editor());
    expect(last).toBe('A {{domains}} B and more');
  });

  it('the picker inserts a variable at the caret', () => {
    render(<Harness initial={'Hello world'} />);
    const textNode = editor().firstChild as Text;
    const range = document.createRange();
    range.setStart(textNode, 6);
    range.collapse(true);
    const sel = window.getSelection()!;
    sel.removeAllRanges();
    sel.addRange(range);
    fireEvent.keyUp(editor());
    fireEvent.click(screen.getByTestId('insert-variable'));
    fireEvent.click(screen.getByTestId('insert-variable-statuses'));
    expect(last).toBe('Hello {{statuses}}world');
  });

  it('find counts matches in the text only and steps with Enter', () => {
    render(<Harness initial={'current one {{domains}} current two current'} />);
    fireEvent.keyDown(editor(), { key: 'f', ctrlKey: true });
    fireEvent.change(screen.getByTestId('find-input'), { target: { value: 'current' } });
    expect(screen.getByTestId('find-count')).toHaveTextContent('1/3');
    fireEvent.keyDown(screen.getByTestId('find-input'), { key: 'Enter' });
    expect(screen.getByTestId('find-count')).toHaveTextContent('2/3');
    expect(editor().getAttribute('data-find-active')).toBe('24-31');
  });

  it('closing find leaves the selection on the active match for editing in place', () => {
    render(<Harness initial={'current one {{domains}} current two'} />);
    fireEvent.keyDown(editor(), { key: 'f', ctrlKey: true });
    fireEvent.change(screen.getByTestId('find-input'), { target: { value: 'current' } });
    fireEvent.keyDown(screen.getByTestId('find-input'), { key: 'Enter' });
    act(() => {
      fireEvent.keyDown(screen.getByTestId('find-input'), { key: 'Escape' });
    });
    expect(window.getSelection()!.toString()).toBe('current');
    expect(editor().contains(window.getSelection()!.anchorNode)).toBe(true);
  });
});

describe('PromptChipEditor drop (security pass 2 nit)', () => {
  it('a drop inserts plain text only, at the caret', () => {
    render(<Harness initial={'Hello world'} />);
    const textNode = editor().firstChild as Text;
    const range = document.createRange();
    range.setStart(textNode, 6);
    range.collapse(true);
    const sel = window.getSelection()!;
    sel.removeAllRanges();
    sel.addRange(range);
    const html = '<b onmouseover="x">bold</b>';
    const ev = fireEvent.drop(editor(), {
      dataTransfer: { getData: (type: string) => (type === 'text/plain' ? 'dropped ' : html) },
    });
    expect(ev).toBe(false); // default prevented
    expect(last).toBe('Hello dropped world');
    expect(editor().querySelector('b')).toBeNull();
  });
});

describe('PromptChipEditor, reviewer pass 2', () => {
  function selectAll() {
    const range = document.createRange();
    range.selectNodeContents(editor());
    const sel = window.getSelection()!;
    sel.removeAllRanges();
    sel.addRange(range);
  }

  it('B1: copy puts the tokens, not the chip labels, on the clipboard', () => {
    render(<Harness initial={'ONE of: {{domains}} | null'} />);
    selectAll();
    const data: Record<string, string> = {};
    fireEvent.copy(editor(), { clipboardData: { setData: (t: string, v: string) => (data[t] = v) } });
    expect(data['text/plain']).toBe('ONE of: {{domains}} | null');
  });

  it('B1: cut puts the tokens on the clipboard and removes the selection', () => {
    render(<Harness initial={'A {{domains}} B'} />);
    selectAll();
    const data: Record<string, string> = {};
    fireEvent.cut(editor(), { clipboardData: { setData: (t: string, v: string) => (data[t] = v) } });
    expect(data['text/plain']).toBe('A {{domains}} B');
    expect(last).toBe('');
  });

  it('B1: dragging a selection carries its tokens', () => {
    render(<Harness initial={'A {{domains}} B'} />);
    selectAll();
    const data: Record<string, string> = {};
    fireEvent.dragStart(editor(), { dataTransfer: { setData: (t: string, v: string) => (data[t] = v) } });
    expect(data['text/plain']).toBe('A {{domains}} B');
  });

  it('a pasted token becomes a chip', () => {
    render(<Harness initial={'Hello world'} />);
    const range = document.createRange();
    range.setStart(editor().firstChild as Text, 6);
    range.collapse(true);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent.paste(editor(), { clipboardData: { getData: () => 'list {{statuses}} ' } });
    expect(last).toBe('Hello list {{statuses}} world');
    expect(editor().querySelector('[data-chip="statuses"]')).not.toBeNull();
  });

  it('B2: Enter inserts a newline into the text itself, never through the browser', () => {
    const exec = vi.fn(() => true);
    (document as unknown as { execCommand: unknown }).execCommand = exec;
    try {
      render(<Harness initial={'ab'} />);
      const range = document.createRange();
      range.setStart(editor().firstChild as Text, 1);
      range.collapse(true);
      window.getSelection()!.removeAllRanges();
      window.getSelection()!.addRange(range);
      fireEvent.keyDown(editor(), { key: 'Enter' });
      expect(exec).not.toHaveBeenCalled();
      expect(last).toBe('a\nb');
    } finally {
      delete (document as unknown as { execCommand?: unknown }).execCommand;
    }
  });

  it('B2: find still lands on a match inside a browser-inserted block', () => {
    render(<Harness initial={'first line'} />);
    const div = document.createElement('div');
    div.textContent = 'current here';
    editor().appendChild(div);
    fireEvent.input(editor());
    expect(last).toBe('first line\ncurrent here');
    fireEvent.keyDown(editor(), { key: 'f', ctrlKey: true });
    fireEvent.change(screen.getByTestId('find-input'), { target: { value: 'current' } });
    act(() => {
      fireEvent.keyDown(screen.getByTestId('find-input'), { key: 'Escape' });
    });
    expect(window.getSelection()!.toString()).toBe('current');
  });

  it('Undo is dropped once a variable is inserted after the removal', () => {
    render(<Harness initial={'A {{domains}} B'} />);
    fireEvent.click(screen.getByTestId('chip-remove-domains'));
    fireEvent.click(screen.getByTestId('insert-variable'));
    fireEvent.click(screen.getByTestId('insert-variable-statuses'));
    expect(screen.queryByTestId('chip-undo')).toBeNull();
  });

  it('the toolbar has a Find button (mock parity)', () => {
    render(<Harness initial={'current'} />);
    fireEvent.click(screen.getByTestId('open-find'));
    expect(screen.getByTestId('find-bar')).toBeInTheDocument();
  });

  it('Escape closes the variable picker', () => {
    render(<Harness initial={'x'} />);
    fireEvent.click(screen.getByTestId('insert-variable'));
    expect(screen.getByTestId('insert-variable-menu')).toBeInTheDocument();
    fireEvent.keyDown(screen.getByTestId('insert-variable-menu'), { key: 'Escape' });
    expect(screen.queryByTestId('insert-variable-menu')).toBeNull();
  });

  it('a variable with no admin page gets no link', () => {
    function NoLink() {
      const [v, setV] = useState('x {{domains}}');
      return (
        <PromptChipEditor
          value={v}
          onChange={setV}
          variables={[{ ...VARS[0], href: '' }]}
          registryNames={['domains']}
        />
      );
    }
    render(<NoLink />);
    expect(editor().querySelector('[data-chip="domains"] a')).toBeNull();
  });
});
