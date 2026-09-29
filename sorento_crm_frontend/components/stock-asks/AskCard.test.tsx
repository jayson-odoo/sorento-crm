/**
 * AC-ST305 (card half): one ask on the landing card shell. Customer + contact, `Asked:`,
 * `Answered:`, the datetime, and ONE button in the top-right slot. No counts, age, badge,
 * Open link or note input. The card body opens; the button never does.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AskCard } from './AskCard';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { StockAsk } from '@/lib/stock-asks';

const ASK: StockAsk = {
  id: 'ask-1',
  customer_name: 'Hock Lee Trading',
  contact_name: 'Ah Seng',
  product_code: 'SRT5674',
  product_name: 'Wiper Blade 24in',
  quantity: 50,
  branch: 'in_stock',
  answer_summary: 'SRT5674 x 50: yes, we have stock, please refer to your salesman to proceed.',
  notified_agent: true,
  notify_skip_reason: null,
  state: 'open',
  note: 'Called, ordering Friday',
  created_at: '2026-09-27T03:00:00Z',
  updated_at: null,
};
const DONE: StockAsk = { ...ASK, id: 'ask-2', state: 'done', done_by: 'Sean Ibrahim', done_at: '2026-09-29T02:00:00Z' };

function setup(ask: StockAsk = ASK, extra: Partial<React.ComponentProps<typeof AskCard>> = {}) {
  const handlers = { onOpen: vi.fn(), onDone: vi.fn(), onReopen: vi.fn() };
  const view = render(<AskCard ask={ask} pending={false} {...handlers} {...extra} />);
  return { ...handlers, ...view };
}

describe('AskCard content (AC-ST305)', () => {
  it('shows customer, contact, Asked, Answered and the datetime', () => {
    const { container } = setup();
    expect(screen.getByText('Hock Lee Trading')).toBeInTheDocument();
    expect(screen.getByText('Ah Seng')).toBeInTheDocument();
    const text = (container.textContent ?? '').replace(/\s+/g, ' ');
    expect(text).toContain('Asked: SRT5674 x 50');
    expect(text).toContain('Answered: Yes, we have stock, please refer to your salesman to proceed.');
    expect(text).toContain(formatDateTimeInMalaysia(ASK.created_at));
  });

  it('shows nothing else: no branch badge, notified chip, age, note, Open link or input', () => {
    const { container } = setup();
    const text = container.textContent ?? '';
    for (const gone of ['In stock', 'Sent', 'Not sent', 'Pending', 'Console', 'Incoming', 'days ago', 'Yesterday', 'Called, ordering Friday']) {
      expect(text).not.toContain(gone);
    }
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.queryByText('Open')).toBeNull();
    expect(screen.getAllByRole('button').map((b) => b.textContent?.trim())).toEqual(['Done']);
  });

  it('a done card offers Reopen (not Done) and names who cleared it', () => {
    setup(DONE);
    expect(screen.queryByRole('button', { name: 'Done' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Reopen' })).toBeInTheDocument();
    expect(screen.getByText(/Done by Sean Ibrahim/)).toBeInTheDocument();
  });
});

describe('AskCard click routing (AC-ST305)', () => {
  it('clicking the card body calls onOpen with the ask', () => {
    const { onOpen, onDone } = setup();
    fireEvent.click(screen.getByText('Hock Lee Trading'));
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen).toHaveBeenCalledWith(ASK);
    expect(onDone).not.toHaveBeenCalled();
  });

  it('Enter on the card opens it', () => {
    const { onOpen } = setup();
    const shell = screen.getByText('Hock Lee Trading').closest('[tabindex], [role="button"]') as HTMLElement;
    expect(shell).not.toBeNull();
    fireEvent.keyDown(shell, { key: 'Enter' });
    expect(onOpen).toHaveBeenCalledWith(ASK);
  });

  it('clicking Done calls onDone(id) and does not open the card', () => {
    const { onOpen, onDone } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onDone).toHaveBeenCalledWith('ask-1');
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('clicking Reopen calls onReopen(id) and does not open the card', () => {
    const { onOpen, onReopen } = setup(DONE);
    fireEvent.click(screen.getByRole('button', { name: 'Reopen' }));
    expect(onReopen).toHaveBeenCalledWith('ask-2');
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('a pending card has its button disabled (AC-ST217)', () => {
    setup(ASK, { pending: true });
    expect(screen.getByRole('button', { name: 'Done' })).toBeDisabled();
  });
});
