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

import { UnlinkDialog } from './UnlinkDialog';

function renderDialog(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

const onOpenChange = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  unplaceOrderInquiryRow.mockReset();
});

describe('UnlinkDialog', () => {
  it('names the purchase order it would untag', () => {
    renderDialog(
      <UnlinkDialog
        open
        onOpenChange={onOpenChange}
        rowId="row-1"
        documentNumber="ZZT-PO-0001"
      />,
    );

    expect(
      screen.getByText(
        'Remove the link to ZZT-PO-0001? That quantity goes back to demand, and the next reorder suggestion counts it again.',
      ),
    ).toBeInTheDocument();
  });

  it('falls back to a generic confirm when no PO number is known', () => {
    renderDialog(
      <UnlinkDialog open onOpenChange={onOpenChange} rowId="row-1" documentNumber={null} />,
    );

    expect(
      screen.getByText(
        "Remove this row's links? The quantity goes back to demand, and the next reorder suggestion counts it again.",
      ),
    ).toBeInTheDocument();
  });

  it('renders nothing when closed', () => {
    renderDialog(
      <UnlinkDialog
        open={false}
        onOpenChange={onOpenChange}
        rowId="row-1"
        documentNumber="ZZT-PO-0001"
      />,
    );

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('unlinks the row and closes on confirm', async () => {
    unplaceOrderInquiryRow.mockResolvedValue({ id: 'row-1', state: 'raised' });

    renderDialog(
      <UnlinkDialog
        open
        onOpenChange={onOpenChange}
        rowId="row-1"
        documentNumber="ZZT-PO-0001"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Unlink' }));

    await waitFor(() => expect(unplaceOrderInquiryRow).toHaveBeenCalledWith('row-1', undefined));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('does nothing on cancel', () => {
    renderDialog(
      <UnlinkDialog
        open
        onOpenChange={onOpenChange}
        rowId="row-1"
        documentNumber="ZZT-PO-0001"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(unplaceOrderInquiryRow).not.toHaveBeenCalled();
  });
});
