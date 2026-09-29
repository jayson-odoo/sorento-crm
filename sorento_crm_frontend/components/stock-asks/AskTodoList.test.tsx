/**
 * AC-ST114, AC-ST115, AC-ST116: the shared to-do body (portal Customer asks, CRM Sales >
 * Customer asks). Presentational: payload in, callbacks out.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { AskTodoList } from './AskTodoList';
import type { StockAsk } from '@/lib/stock-asks';
import type { AskTodoPayload } from '@/lib/stock-asks-todo';

const TODAY_START = '2026-09-28T16:00:00Z';

function ask(over: Partial<StockAsk> & { id: string }): StockAsk {
  return {
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
    note: null,
    created_at: '2026-09-29T01:00:00Z',
    updated_at: null,
    ...over,
  };
}

const OLD = ask({
  id: 'old',
  customer_name: 'Old Customer',
  product_code: 'SRT-OLD',
  quantity: 7,
  branch: 'no_incoming',
  created_at: '2026-09-27T05:00:00Z', // two Malaysia days before 29 Sep
});
const NEW = ask({ id: 'new', customer_name: 'New Customer', product_code: 'SRT-NEW' });
const DONE = ask({
  id: 'done1',
  customer_name: 'Finished Customer',
  product_code: 'SRT-DONE',
  state: 'done',
  done_by: 'Sean Ibrahim',
  done_at: '2026-09-29T02:00:00Z',
});

function payload(over: Partial<AskTodoPayload> = {}): AskTodoPayload {
  return { today_start: TODAY_START, open: [OLD, NEW], done_today: [DONE], truncated: false, ...over };
}

function setup(p: AskTodoPayload | null, extra: Partial<React.ComponentProps<typeof AskTodoList>> = {}) {
  const handlers = { onDone: vi.fn(), onReopen: vi.fn(), onNote: vi.fn() };
  const view = render(<AskTodoList payload={p} loading={false} {...handlers} {...extra} />);
  return { ...handlers, ...view };
}

describe('AskTodoList counts and groups (AC-ST114)', () => {
  it('renders the counts line with the needs-attention count destructive when above zero', () => {
    setup(payload());
    const counts = screen.getByTestId('ask-todo-counts');
    expect(counts.textContent?.replace(/\s+/g, ' ').trim()).toBe('Open 2 · Needs attention 1 · Done today 1');
    expect(within(counts).getByText('1', { selector: '.text-destructive' })).toBeInTheDocument();
  });

  it('does not colour the needs-attention count at zero', () => {
    setup(payload({ open: [NEW] }));
    expect(screen.getByTestId('ask-todo-counts').querySelector('.text-destructive')).toBeNull();
  });

  it('renders the group headings in order: Needs attention, Today, Done today', () => {
    setup(payload());
    const headings = screen.getAllByRole('heading').map((h) => h.textContent);
    expect(headings).toEqual(['Needs attention', 'Today', 'Done today']);
  });

  it('renders a row with customer, contact, CODE x Q, branch badge, answer, time and a Done button', () => {
    setup(payload({ open: [NEW], done_today: [] }));
    const row = screen.getByText('New Customer').closest('li') as HTMLElement;
    expect(row.textContent).toContain('Ah Seng');
    expect(row.textContent).toContain('SRT-NEW x 50');
    expect(within(row).getByText('In stock')).toBeInTheDocument();
    expect(within(row).getByText(/yes, we have stock/)).toBeInTheDocument();
    expect(row.textContent).toMatch(/\d{1,2}\/\d{2}\/2026/); // the time asked, Malaysia wall clock
    expect(within(row).getByRole('button', { name: 'Done' })).toBeInTheDocument();
  });

  it('shows an age label on a needs-attention row and none on a today row', () => {
    setup(payload());
    const old = screen.getByText('Old Customer').closest('li') as HTMLElement;
    const fresh = screen.getByText('New Customer').closest('li') as HTMLElement;
    expect(within(old).getByText('2 days ago')).toBeInTheDocument();
    expect(fresh.textContent).not.toMatch(/days? ago|Yesterday/);
  });

  it('names the agent on line 1 only when showAgent is set', () => {
    const withCode = payload({ open: [{ ...NEW, agent_code: 'SEAN I' }], done_today: [] });
    const { unmount } = setup(withCode, { showAgent: true });
    expect(screen.getByText('SEAN I')).toBeInTheDocument();
    unmount();
    setup(withCode);
    expect(screen.queryByText('SEAN I')).toBeNull();
  });
});

describe('AskTodoList actions (AC-ST115)', () => {
  it('calls onDone with the ask id', () => {
    const { onDone } = setup(payload());
    const row = screen.getByText('New Customer').closest('li') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: 'Done' }));
    expect(onDone).toHaveBeenCalledWith('new');
  });

  it('renders a done row under Done today with Done by, the time and a Reopen that calls onReopen', () => {
    const { onReopen } = setup(payload());
    const section = screen.getByRole('heading', { name: 'Done today' }).closest('section') as HTMLElement;
    const row = within(section).getByText('Finished Customer').closest('li') as HTMLElement;
    expect(row.textContent).toContain('Done by Sean Ibrahim');
    expect(within(row).queryByRole('button', { name: 'Done' })).toBeNull();
    fireEvent.click(within(row).getByRole('button', { name: 'Reopen' }));
    expect(onReopen).toHaveBeenCalledWith('done1');
  });

  it('saves the note through onNote on blur, and not when unchanged', () => {
    const { onNote } = setup(payload({ open: [NEW], done_today: [] }));
    const box = screen.getByLabelText('Note for SRT-NEW');
    fireEvent.blur(box);
    expect(onNote).not.toHaveBeenCalled();
    fireEvent.change(box, { target: { value: 'Called, ordering Friday' } });
    fireEvent.blur(box);
    expect(onNote).toHaveBeenCalledWith('new', 'Called, ordering Friday');
  });
});

describe('AskTodoList states (AC-ST116)', () => {
  it('renders Nothing waiting with the hint and no button when there is nothing at all', () => {
    setup(payload({ open: [], done_today: [] }));
    expect(screen.getByText('Nothing waiting')).toBeInTheDocument();
    expect(screen.getByText(/land here/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('still shows Nothing waiting and the cleared rows when only done rows remain', () => {
    setup(payload({ open: [] }));
    expect(screen.getByText('Nothing waiting')).toBeInTheDocument();
    expect(screen.getByText('Finished Customer')).toBeInTheDocument();
  });

  it('shows the truncated notice only when the payload is truncated', () => {
    const { unmount } = setup(payload({ truncated: true }));
    expect(screen.getByText('Showing the oldest 500 open asks')).toBeInTheDocument();
    unmount();
    setup(payload());
    expect(screen.queryByText('Showing the oldest 500 open asks')).toBeNull();
  });

  it('renders a loading state and an error state instead of rows', () => {
    const { unmount } = render(
      <AskTodoList payload={null} loading onDone={vi.fn()} onReopen={vi.fn()} onNote={vi.fn()} />,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
    unmount();
    render(
      <AskTodoList payload={null} loading={false} error="Boom" onDone={vi.fn()} onReopen={vi.fn()} onNote={vi.fn()} />,
    );
    expect(screen.getByText('Boom')).toBeInTheDocument();
  });
});
