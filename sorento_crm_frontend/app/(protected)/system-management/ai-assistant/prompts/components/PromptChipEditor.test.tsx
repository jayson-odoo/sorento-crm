/**
 * PROMPT-DYNAMIC R5a (owner, 30 Sep 2026: "it needs to stay visualized during edit time,
 * all the time; it should be a variable wired into the prompt; if I want to overwrite I can
 * remove the variable"). Red before the component exists.
 */
import React, { useState } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
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
