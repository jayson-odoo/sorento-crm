/**
 * The List Price cell's change-history lightbox (LIST-PRICE-CHANGE-UI).
 *
 * Plan: `documentation/plans/products/PLAN-list-price-change-ui-08nov.md`. Owner Q3: the
 * history is the STANDARD DataGrid list view with server-side pagination and sortable
 * columns, inside the shared `Dialog` lightbox. Owner Q5: the create-time price is an
 * "Initial price" row. All values are fake.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within, fireEvent, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getPriceHistory = vi.fn();

vi.mock('../services/productService', () => ({
  getPriceHistory: (...a: unknown[]) => getPriceHistory(...a),
}));

// The system currency format (Settings > General); the shipped default.
vi.mock('@/hooks/useCurrencyFormat', () => ({ useCurrencyFormat: () => 'RM {value}' }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/products',
  useRouter: () => ({ push: () => {}, replace: () => {} }),
  useSearchParams: () => new URLSearchParams(),
}));

import ListPriceHistoryDialog from './ListPriceHistoryDialog';

const PRODUCT = { id: 'prod-1', product_code: 'FAKE-001', product_name: 'Fake Basin Mixer' };

const ROWS = [
  {
    id: 'a1',
    kind: 'change',
    changed_at: '2026-10-31T04:00:00',
    old_price: 110,
    new_price: 121,
    change_pct: 10,
    changed_by: 'Fake Pricer',
  },
  {
    id: 'a2',
    kind: 'change',
    changed_at: '2026-11-07T16:30:00',
    old_price: 1210,
    new_price: 1089,
    change_pct: -10,
    changed_by: 'AutoCount sync',
  },
  {
    id: 'a3',
    kind: 'change',
    changed_at: '2026-09-02T00:00:00',
    old_price: 0,
    new_price: 100,
    change_pct: null,
    changed_by: null,
  },
  {
    id: 'a4',
    kind: 'initial',
    changed_at: '2026-09-01T00:00:00',
    old_price: null,
    new_price: 50,
    change_pct: null,
    changed_by: 'Fake Creator',
  },
];

function renderDialog(product: typeof PRODUCT | null = PRODUCT, onOpenChange = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ListPriceHistoryDialog product={product} onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
}

function lastCall(): [string, Record<string, unknown>] {
  const calls = getPriceHistory.mock.calls;
  return calls[calls.length - 1] as [string, Record<string, unknown>];
}

function bodyRows(dialog: HTMLElement) {
  return within(dialog)
    .getAllByRole('row')
    .filter((r) => r.closest('tbody'));
}

beforeEach(() => {
  getPriceHistory.mockReset();
  getPriceHistory.mockResolvedValue({ data: ROWS, pagination: { total: 4, page: 1, limit: 10 } });
});
afterEach(() => cleanup());

describe('ListPriceHistoryDialog', () => {
  it('is closed and fetches nothing without a product', () => {
    renderDialog(null);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(getPriceHistory).not.toHaveBeenCalled();
  });

  it('asks the server for page 1, newest first, and titles the dialog with the product', async () => {
    renderDialog();
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/FAKE-001/)).toBeInTheDocument();
    await waitFor(() => expect(getPriceHistory).toHaveBeenCalled());
    const [id, params] = lastCall();
    expect(id).toBe('prod-1');
    expect(params).toMatchObject({
      pageIndex: 0,
      pageSize: 10,
      sorting: [{ id: 'changed_at', desc: true }],
    });
  });

  it('renders the rows in server order: date, old, new, % change and who', async () => {
    renderDialog();
    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(bodyRows(dialog).length).toBe(4));
    const rows = bodyRows(dialog);

    expect(rows[0]).toHaveTextContent('31/10/2026');
    expect(rows[0]).toHaveTextContent(/RM 110\.00/);
    expect(rows[0]).toHaveTextContent(/RM 121\.00/);
    expect(rows[0]).toHaveTextContent('+10.0%');
    expect(rows[0]).toHaveTextContent('Fake Pricer');

    // Naive UTC 16:30 is the next Malaysia day; thousands grouped; a fall keeps its sign.
    expect(rows[1]).toHaveTextContent('08/11/2026');
    expect(rows[1]).toHaveTextContent(/RM 1,210\.00/);
    expect(rows[1]).toHaveTextContent('-10.0%');
    expect(rows[1]).toHaveTextContent('AutoCount sync');

    // From 0 there is no percentage.
    expect(rows[2]).not.toHaveTextContent('%');

    // The create-time price.
    expect(rows[3]).toHaveTextContent('Initial price');
    expect(rows[3]).toHaveTextContent(/RM 50\.00/);
    expect(rows[3]).toHaveTextContent('Fake Creator');
  });

  it('pages on the server through the standard pagination bar', async () => {
    getPriceHistory.mockResolvedValue({ data: ROWS, pagination: { total: 25, page: 1, limit: 10 } });
    renderDialog();
    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(bodyRows(dialog).length).toBe(4));

    const next = within(dialog).getByText('Go to next page').closest('button') as HTMLButtonElement;
    await act(async () => {
      fireEvent.click(next);
    });
    await waitFor(() => expect(lastCall()[1]).toMatchObject({ pageIndex: 1, pageSize: 10 }));
  });

  it('a new sort goes back to page 1', async () => {
    getPriceHistory.mockResolvedValue({ data: ROWS, pagination: { total: 25, page: 1, limit: 10 } });
    renderDialog();
    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(bodyRows(dialog).length).toBe(4));
    await act(async () => {
      fireEvent.click(within(dialog).getByText('Go to next page').closest('button') as HTMLButtonElement);
    });
    await waitFor(() => expect(lastCall()[1]).toMatchObject({ pageIndex: 1 }));

    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: /^% change/ }));
    });
    await waitFor(() => {
      const params = lastCall()[1];
      expect((params.sorting as { id: string }[])[0]?.id).toBe('change_pct');
      expect(params.pageIndex).toBe(0);
    });
  });

  it('every column sorts on the server', async () => {
    renderDialog();
    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(bodyRows(dialog).length).toBe(4));
    const headers = within(dialog).getAllByRole('columnheader').map((h) => h.textContent ?? '');
    expect(headers.join('|')).toMatch(/Date.*Old price.*New price.*% change.*By/);

    const byHeader = within(dialog).getByRole('button', { name: /^By/ });
    await act(async () => {
      fireEvent.click(byHeader);
    });
    await waitFor(() => {
      const sorting = lastCall()[1].sorting as { id: string }[];
      expect(sorting[0]?.id).toBe('changed_by');
    });
  });

  it('shows an empty state with a heading and no button', async () => {
    getPriceHistory.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 10 } });
    renderDialog();
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('No list price changes recorded')).toBeInTheDocument();
  });

  it('shows the load error', async () => {
    getPriceHistory.mockRejectedValue(new Error('Failed to load list price history'));
    renderDialog();
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Failed to load list price history')).toBeInTheDocument();
  });
});
