/**
 * Untag (section G): a confirm dialog, per the CRUD standard - it undoes a deliberate,
 * evidence-carrying action (the backend deletes the audit claim), not a toggle.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const unplaceOrderInquiryRow = vi.fn();

vi.mock('../services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderInquiryService')>();
  return {
    ...actual,
    unplaceOrderInquiryRow: (...args: unknown[]) => unplaceOrderInquiryRow(...args),
  };
});

import { UnplaceFromPoDialog } from './UnplaceFromPoDialog';

function renderDialog(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

const onOpenChange = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  unplaceOrderInquiryRow.mockReset();
});

describe('UnplaceFromPoDialog', () => {
  it('names the purchase order it would untag', () => {
    renderDialog(
      <UnplaceFromPoDialog
        open
        onOpenChange={onOpenChange}
        rowId="row-1"
        poNumber="ZZT-PO-0001"
      />,
    );

    expect(
      screen.getByText(
        'Remove the tag to ZZT-PO-0001? This row goes back to raised, and the next reorder suggestion counts it again.',
      ),
    ).toBeInTheDocument();
  });

  it('falls back to a generic confirm when no PO number is known', () => {
    renderDialog(
      <UnplaceFromPoDialog open onOpenChange={onOpenChange} rowId="row-1" poNumber={null} />,
    );

    expect(
      screen.getByText(
        'Remove this tag? This row goes back to raised, and the next reorder suggestion counts it again.',
      ),
    ).toBeInTheDocument();
  });

  it('renders nothing when closed', () => {
    renderDialog(
      <UnplaceFromPoDialog
        open={false}
        onOpenChange={onOpenChange}
        rowId="row-1"
        poNumber="ZZT-PO-0001"
      />,
    );

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('unplaces the row and closes on confirm', async () => {
    unplaceOrderInquiryRow.mockResolvedValue({ id: 'row-1', state: 'raised' });

    renderDialog(
      <UnplaceFromPoDialog
        open
        onOpenChange={onOpenChange}
        rowId="row-1"
        poNumber="ZZT-PO-0001"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Unplace' }));

    await waitFor(() => expect(unplaceOrderInquiryRow).toHaveBeenCalledWith('row-1'));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('does nothing on cancel', () => {
    renderDialog(
      <UnplaceFromPoDialog
        open
        onOpenChange={onOpenChange}
        rowId="row-1"
        poNumber="ZZT-PO-0001"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(unplaceOrderInquiryRow).not.toHaveBeenCalled();
  });
});
