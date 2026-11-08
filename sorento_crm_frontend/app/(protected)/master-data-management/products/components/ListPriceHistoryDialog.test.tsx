/**
 * The List Price cell's change-history lightbox (LIST-PRICE-CHANGE-UI).
 *
 * Plan: `documentation/plans/products/PLAN-list-price-change-ui-08nov.md`.
 *
 * Built from the shared `Dialog` (every Dialog is a modal lightbox) and `Table`; reads
 * `GET /master-data/products/{id}/list-price-history` through `useProductPriceHistory`.
 * All values are fake.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getPriceHistory = vi.fn();

vi.mock('../services/productService', () => ({
  getPriceHistory: (...a: unknown[]) => getPriceHistory(...a),
}));

import ListPriceHistoryDialog from './ListPriceHistoryDialog';

const PRODUCT = { id: 'prod-1', product_code: 'FAKE-001', product_name: 'Fake Basin Mixer' };

function renderDialog(product: typeof PRODUCT | null = PRODUCT, onOpenChange = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ListPriceHistoryDialog product={product} onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getPriceHistory.mockReset();
});
afterEach(() => cleanup());

describe('ListPriceHistoryDialog', () => {
  it('is closed and fetches nothing without a product', () => {
    renderDialog(null);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(getPriceHistory).not.toHaveBeenCalled();
  });

  it('lists the changes newest first: date, old -> new, % change and who', async () => {
    getPriceHistory.mockResolvedValue({
      data: [
        {
          changed_at: '2026-10-31T04:00:00',
          old_price: 110,
          new_price: 121,
          change_pct: 10,
          changed_by: 'Fake Pricer',
        },
        {
          changed_at: '2026-11-07T16:30:00',
          old_price: 1210,
          new_price: 1089,
          change_pct: -10,
          changed_by: 'AutoCount sync',
        },
        {
          changed_at: '2026-09-01T00:00:00',
          old_price: 0,
          new_price: 100,
          change_pct: null,
          changed_by: null,
        },
      ],
      total: 3,
      truncated: false,
    });
    renderDialog();

    const dialog = await screen.findByRole('dialog');
    expect(getPriceHistory).toHaveBeenCalledWith('prod-1');
    expect(within(dialog).getByText(/FAKE-001/)).toBeInTheDocument();

    await waitFor(() => expect(within(dialog).getAllByRole('row').length).toBe(4)); // header + 3
    const rows = within(dialog).getAllByRole('row').slice(1);

    // Server order is kept (it is already newest first).
    expect(rows[0]).toHaveTextContent('31/10/2026');
    expect(rows[0]).toHaveTextContent(/MYR\s110\.00/);
    expect(rows[0]).toHaveTextContent(/MYR\s121\.00/);
    expect(rows[0]).toHaveTextContent('+10.0%');
    expect(rows[0]).toHaveTextContent('Fake Pricer');

    // Naive UTC 16:30 is the next Malaysia day; thousands are grouped; negative keeps its sign.
    expect(rows[1]).toHaveTextContent('08/11/2026');
    expect(rows[1]).toHaveTextContent(/MYR\s1,210\.00/);
    expect(rows[1]).toHaveTextContent('-10.0%');
    expect(rows[1]).toHaveTextContent('AutoCount sync');

    // From 0 there is no percentage.
    expect(rows[2]).toHaveTextContent('New price');
    expect(rows[2]).not.toHaveTextContent('%');

    expect(within(dialog).queryByText(/Showing the latest/)).toBeNull();
  });

  it('says when the list is capped', async () => {
    getPriceHistory.mockResolvedValue({
      data: [
        { changed_at: '2026-10-31T04:00:00', old_price: 1, new_price: 2, change_pct: 100, changed_by: null },
      ],
      total: 55,
      truncated: true,
    });
    renderDialog();
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Showing the latest 1 of 55 changes')).toBeInTheDocument();
  });

  it('shows an empty state with a heading and no button', async () => {
    getPriceHistory.mockResolvedValue({ data: [], total: 0, truncated: false });
    renderDialog();
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('No list price changes recorded')).toBeInTheDocument();
    expect(within(dialog).queryByRole('table')).toBeNull();
    // The only button is the dialog's own close control.
    expect(within(dialog).getAllByRole('button').every((b) => /close/i.test(b.getAttribute('aria-label') ?? b.textContent ?? ''))).toBe(true);
  });

  it('shows the load error', async () => {
    getPriceHistory.mockRejectedValue(new Error('Failed to load list price history'));
    renderDialog();
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Failed to load list price history')).toBeInTheDocument();
  });
});
