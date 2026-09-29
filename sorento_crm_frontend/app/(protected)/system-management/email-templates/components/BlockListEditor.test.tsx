/**
 * D5, AC-EM040-044 - the ordered block list editor: renders blocks in order,
 * Move up/down reorders (with the first/last button disabled), Add block
 * appends a default of the chosen type, Remove drops one, and editing a
 * block's own settings (facts rows, button label) patches it in place.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { EmailBlock } from '../types/emailTemplate.types';
import { BlockListEditor } from './BlockListEditor';

function blocks(): EmailBlock[] {
  return [
    { id: 'b1', type: 'brand_header' },
    { id: 'b2', type: 'heading', text: 'Reset your password', align: 'left' },
    { id: 'b3', type: 'button', label: 'Reset password', url: '{{ reset_link }}' },
  ];
}

describe('BlockListEditor', () => {
  it('renders every block in order with its type label', () => {
    render(<BlockListEditor blocks={blocks()} onChange={vi.fn()} />);

    const labels = screen.getAllByText(/Brand header|Heading|CTA button/);
    expect(labels.map((el) => el.textContent)).toEqual(['Brand header', 'Heading', 'CTA button']);
  });

  it('Move down reorders and emits the new order; the last block cannot move down', () => {
    const onChange = vi.fn();
    render(<BlockListEditor blocks={blocks()} onChange={onChange} />);

    const moveDownButtons = screen.getAllByRole('button', { name: 'Move down' });
    expect(moveDownButtons[2]).toBeDisabled();

    fireEvent.click(moveDownButtons[0]);

    const emitted = onChange.mock.calls[0][0] as EmailBlock[];
    expect(emitted.map((b) => b.id)).toEqual(['b2', 'b1', 'b3']);
  });

  it('Move up reorders; the first block cannot move up', () => {
    const onChange = vi.fn();
    render(<BlockListEditor blocks={blocks()} onChange={onChange} />);

    const moveUpButtons = screen.getAllByRole('button', { name: 'Move up' });
    expect(moveUpButtons[0]).toBeDisabled();

    fireEvent.click(moveUpButtons[2]);

    const emitted = onChange.mock.calls[0][0] as EmailBlock[];
    expect(emitted.map((b) => b.id)).toEqual(['b1', 'b3', 'b2']);
  });

  it('Add block appends a default block of the chosen type', async () => {
    const onChange = vi.fn();
    render(<BlockListEditor blocks={blocks()} onChange={onChange} />);

    await userEvent.click(screen.getByRole('button', { name: /Add block/ }));
    await userEvent.click(screen.getByRole('menuitem', { name: 'Facts table' }));

    const emitted = onChange.mock.calls[0][0] as EmailBlock[];
    expect(emitted).toHaveLength(4);
    const added = emitted[3];
    expect(added.type).toBe('facts');
    expect(added).toMatchObject({ rows: [], hide_empty: true });
  });

  it('Remove drops the block', () => {
    const onChange = vi.fn();
    render(<BlockListEditor blocks={blocks()} onChange={onChange} />);

    fireEvent.click(screen.getAllByRole('button', { name: 'Remove block' })[1]);

    const emitted = onChange.mock.calls[0][0] as EmailBlock[];
    expect(emitted.map((b) => b.id)).toEqual(['b1', 'b3']);
  });

  it('editing the button label patches only that block', () => {
    const onChange = vi.fn();
    render(<BlockListEditor blocks={blocks()} onChange={onChange} />);

    const labelInput = screen.getByDisplayValue('Reset password');
    fireEvent.change(labelInput, { target: { value: 'Reset my password' } });

    const emitted = onChange.mock.calls[0][0] as EmailBlock[];
    expect(emitted[2]).toMatchObject({ id: 'b3', type: 'button', label: 'Reset my password' });
    expect(emitted[0]).toEqual(blocks()[0]);
  });

  it('facts rows: add a row then edit its label updates the emitted value', () => {
    const factsBlocks: EmailBlock[] = [{ id: 'f1', type: 'facts', rows: [], hide_empty: true }];
    let current = factsBlocks;
    const onChange = vi.fn((next: EmailBlock[]) => {
      current = next;
    });
    const { rerender } = render(<BlockListEditor blocks={current} onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: 'Add row' }));
    rerender(<BlockListEditor blocks={current} onChange={onChange} />);

    const labelInput = screen.getByLabelText('Fact label');
    fireEvent.change(labelInput, { target: { value: 'Customer' } });

    const last = onChange.mock.calls[onChange.mock.calls.length - 1][0] as EmailBlock[];
    expect(last[0]).toMatchObject({ type: 'facts', rows: [{ label: 'Customer', value: '' }] });
  });

  it('custom text: the HTML toggle shows a textarea editing the raw html', () => {
    const customBlocks: EmailBlock[] = [{ id: 'c1', type: 'custom_text', html: '<p>Hi</p>' }];
    render(<BlockListEditor blocks={customBlocks} onChange={vi.fn()} />);

    fireEvent.click(screen.getByLabelText('HTML'));

    const textarea = screen.getByLabelText('HTML source') as HTMLTextAreaElement;
    expect(textarea.value).toBe('<p>Hi</p>');
  });

  it('custom text with a table or Jinja tag opens in HTML mode so the rich editor cannot mangle it', () => {
    const html = '<table><tr>{% for l in lines %}<td>{{ l.item_code }}</td>{% endfor %}</tr></table>';
    const customBlocks: EmailBlock[] = [{ id: 'c2', type: 'custom_text', html }];
    render(<BlockListEditor blocks={customBlocks} onChange={vi.fn()} />);

    const textarea = screen.getByLabelText('HTML source') as HTMLTextAreaElement;
    expect(textarea.value).toBe(html);
  });
});
