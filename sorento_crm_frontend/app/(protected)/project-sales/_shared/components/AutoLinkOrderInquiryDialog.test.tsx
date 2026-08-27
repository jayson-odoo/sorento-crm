/**
 * "Auto link all" (AC-D9): the dialog carries the Purchase order cut off date, moved here
 * from the toolbar (item 12, `PLAN-scm-oi-draft-links.md`) - so the label reads "Purchase
 * order cut off", not "Link up to", and the date travels on the request whichever way the
 * page is holding it: a chosen date, a cleared box, or nothing said at all.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const autoPlaceOrderInquiryRows = vi.fn();

vi.mock('../services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderInquiryService')>();
  return {
    ...actual,
    autoPlaceOrderInquiryRows: (...args: unknown[]) => autoPlaceOrderInquiryRows(...args),
  };
});

import { AutoLinkOrderInquiryDialog } from './AutoLinkOrderInquiryDialog';

function renderDialog(props: Partial<React.ComponentProps<typeof AutoLinkOrderInquiryDialog>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onOpenChange = vi.fn();
  const utils = render(
    <QueryClientProvider client={client}>
      <AutoLinkOrderInquiryDialog open onOpenChange={onOpenChange} {...props} />
    </QueryClientProvider>,
  );
  return { ...utils, onOpenChange };
}

beforeEach(() => {
  vi.clearAllMocks();
  autoPlaceOrderInquiryRows.mockResolvedValue({ placed_rows: 0, allocations: 0, products_touched: 0 });
});

describe('AutoLinkOrderInquiryDialog (AC-D9)', () => {
  it('labels the date "Purchase order cut off", never "Link up to"', () => {
    renderDialog();
    expect(screen.getByText('Purchase order cut off')).toBeInTheDocument();
    expect(screen.queryByText('Link up to')).not.toBeInTheDocument();
  });

  it('the date the page hands in sits in the input', () => {
    renderDialog({ linkUpTo: '2026-12-31' });
    const input = screen.getByTestId('auto-link-cut-off') as HTMLInputElement;
    expect(input.value).toBe('2026-12-31');
  });

  it('sends the date on the request when one is set', async () => {
    renderDialog({ linkUpTo: '2026-12-31' });

    fireEvent.click(screen.getByRole('button', { name: 'Auto link all' }));

    await waitFor(() =>
      expect(autoPlaceOrderInquiryRows).toHaveBeenCalledWith({ link_up_to: '2026-12-31' }),
    );
  });

  it('sends an explicit no-horizon when the box is cleared, defaulting to "No link horizon"', async () => {
    renderDialog({ linkUpTo: '', horizonCleared: true });

    expect(screen.getByText('No link horizon')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Auto link all' }));

    await waitFor(() =>
      expect(autoPlaceOrderInquiryRows).toHaveBeenCalledWith({ link_horizon: 'none' }),
    );
  });

  it('sends nothing about the horizon when nobody has chosen - the server uses the plan default', async () => {
    renderDialog();

    fireEvent.click(screen.getByRole('button', { name: 'Auto link all' }));

    await waitFor(() => expect(autoPlaceOrderInquiryRows).toHaveBeenCalledWith({}));
  });

  it('publishes the chosen date back to the page so it is remembered', () => {
    const onHorizonChange = vi.fn();
    renderDialog({ onHorizonChange });

    fireEvent.change(screen.getByTestId('auto-link-cut-off'), {
      target: { value: '2027-01-15' },
    });

    expect(onHorizonChange).toHaveBeenCalledWith('2027-01-15', false);
  });

  it('closes on success and never fires the cascade before the press', async () => {
    const { onOpenChange } = renderDialog();
    expect(autoPlaceOrderInquiryRows).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Auto link all' }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('names what it is about to do, so cancel is a real choice', () => {
    renderDialog();
    expect(
      screen.getByText(
        'Link open order rows to outstanding documents, nearest location and earliest purchase order first?',
      ),
    ).toBeInTheDocument();
  });

  it('Cancel closes without running anything', () => {
    const { onOpenChange } = renderDialog();

    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Cancel' }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(autoPlaceOrderInquiryRows).not.toHaveBeenCalled();
  });
});
