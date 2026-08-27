/**
 * Purchasing refuses a BATCH, with ONE reason (item 15, AC-D6, R8).
 *
 * The reason is asked for once and carried onto every ticked row: an empty one is refused
 * with nothing sent, and a real submit sends `{row_ids, reason}` exactly once.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const rejectOrderInquiryRows = vi.fn();

vi.mock('../services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderInquiryService')>();
  return {
    ...actual,
    rejectOrderInquiryRows: (...args: unknown[]) => rejectOrderInquiryRows(...args),
  };
});

import { BulkRejectOrderInquiryDialog } from './BulkRejectOrderInquiryDialog';

function renderDialog(props: Partial<React.ComponentProps<typeof BulkRejectOrderInquiryDialog>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onOpenChange = vi.fn();
  const onRejected = vi.fn();
  const utils = render(
    <QueryClientProvider client={client}>
      <BulkRejectOrderInquiryDialog
        open
        onOpenChange={onOpenChange}
        rowIds={['row-1', 'row-2']}
        onRejected={onRejected}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { ...utils, onOpenChange, onRejected };
}

beforeEach(() => {
  vi.clearAllMocks();
  rejectOrderInquiryRows.mockResolvedValue({
    rejected: 2,
    results: [
      { row_id: 'row-1', ok: true },
      { row_id: 'row-2', ok: true },
    ],
  });
});

describe('BulkRejectOrderInquiryDialog (AC-D6)', () => {
  it('names the count in the title', () => {
    renderDialog();
    expect(screen.getByText('Reject 2 rows?')).toBeInTheDocument();
  });

  it('names one row in the singular', () => {
    renderDialog({ rowIds: ['row-1'] });
    expect(screen.getByText('Reject 1 row?')).toBeInTheDocument();
  });

  it('refuses an empty reason and sends nothing', () => {
    renderDialog();

    fireEvent.click(screen.getByRole('button', { name: /Reject 2 rows/ }));

    expect(screen.getByText('A reason is required to reject.')).toBeInTheDocument();
    expect(rejectOrderInquiryRows).not.toHaveBeenCalled();
  });

  it('refuses a whitespace-only reason too', () => {
    renderDialog();

    fireEvent.change(screen.getByPlaceholderText(/Why can this not be bought/), {
      target: { value: '   ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Reject 2 rows/ }));

    expect(screen.getByText('A reason is required to reject.')).toBeInTheDocument();
    expect(rejectOrderInquiryRows).not.toHaveBeenCalled();
  });

  it('sends {row_ids, reason} exactly once on a real reason', async () => {
    renderDialog();

    fireEvent.change(screen.getByPlaceholderText(/Why can this not be bought/), {
      target: { value: 'Factory closed until November' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Reject 2 rows/ }));

    await waitFor(() =>
      expect(rejectOrderInquiryRows).toHaveBeenCalledWith(
        ['row-1', 'row-2'],
        'Factory closed until November',
      ),
    );
    expect(rejectOrderInquiryRows).toHaveBeenCalledTimes(1);
  });

  it('closes and clears the page selection once the batch went through', async () => {
    const { onOpenChange, onRejected } = renderDialog();

    fireEvent.change(screen.getByPlaceholderText(/Why can this not be bought/), {
      target: { value: 'Factory closed until November' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Reject 2 rows/ }));

    await waitFor(() => expect(onRejected).toHaveBeenCalled());
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('resets the reason box each time the dialog opens', () => {
    const { rerender } = render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <BulkRejectOrderInquiryDialog
          open
          onOpenChange={vi.fn()}
          rowIds={['row-1']}
        />
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByPlaceholderText(/Why can this not be bought/), {
      target: { value: 'Some reason' },
    });
    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <BulkRejectOrderInquiryDialog
          open={false}
          onOpenChange={vi.fn()}
          rowIds={['row-1']}
        />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <BulkRejectOrderInquiryDialog
          open
          onOpenChange={vi.fn()}
          rowIds={['row-1']}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByPlaceholderText(/Why can this not be bought/)).toHaveValue('');
  });
});
