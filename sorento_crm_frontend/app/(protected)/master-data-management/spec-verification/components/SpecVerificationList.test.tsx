/**
 * SpecVerificationList - the worklist screen (PR 3).
 *
 * The service layer is mocked; the real hooks (`useSpecVerification`) and the real
 * shared `DataGrid` run, so the cache-patch behaviour (AC-D.22: acted row updates in
 * place, no re-sort) is exercised for real, not reimplemented in the test.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render,
  screen,
  cleanup,
  waitFor,
  fireEvent,
  within,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: async () => {},
    isLoading: false,
  }),
}));

const usePermissions = vi.fn();
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => usePermissions(),
}));

const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  push: vi.fn(),
  replace: vi.fn(),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  usePathname: () => '/master-data-management/spec-verification',
  useSearchParams: () => nav.params,
}));

const getSpecVerificationWorklist = vi.fn();
const verifySpecBulk = vi.fn();
const unverifySpecBulk = vi.fn();

vi.mock('../services/specVerificationService', () => ({
  getSpecVerificationWorklist: (...a: unknown[]) =>
    getSpecVerificationWorklist(...a),
  verifySpecBulk: (...a: unknown[]) => verifySpecBulk(...a),
  unverifySpecBulk: (...a: unknown[]) => unverifySpecBulk(...a),
}));

import SpecVerificationList from './SpecVerificationList';
import type {
  SpecVerificationRow,
  VerificationState,
} from '../types/specVerification.types';

function row(
  code: string,
  state: VerificationState,
  overrides: Partial<SpecVerificationRow> = {},
): SpecVerificationRow {
  return {
    product_id: `id-${code}`,
    product_code: code,
    product_name: `Product ${code}`,
    class_label: 'Kitchen Sink',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: {
      have: 2,
      applicable: 3,
      items: [
        {
          spec_key: 'material',
          label: 'Material',
          value: { value: 'ceramic' },
        },
        {
          spec_key: 'dim_height',
          label: 'Height',
          value: { value: 770, unit: 'mm' },
        },
        { spec_key: 'finish', label: 'Finish or colour', value: null },
      ],
    },
    open_exceptions: 0,
    values_hash: `hash-${code}`,
    verification: {
      state,
      verified_by_name: state === 'verified' ? 'Jay Odoo' : null,
      verified_at: state === 'verified' ? '2026-08-01T09:00:00' : null,
      invalidated_at: null,
      invalidated_reason: null,
      invalidated_by_name: null,
      invalidated_diff: null,
    },
    ...overrides,
  };
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SpecVerificationList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  nav.params = new URLSearchParams();
  usePermissions.mockReturnValue({
    permissionSet: new Set(['master_data.products.edit']),
  });
});

afterEach(() => cleanup());

describe('loading state', () => {
  it('shows the progress-line skeleton and a disabled search box while the worklist loads', () => {
    getSpecVerificationWorklist.mockReturnValue(new Promise(() => {})); // never resolves
    renderList();

    expect(
      screen.queryByTestId('verification-progress')?.textContent ?? '',
    ).not.toContain('Verified');
    expect(screen.getByPlaceholderText('Search code or name')).toBeDisabled();
  });
});

describe('error state', () => {
  it('renders the failure message with a Retry action', async () => {
    getSpecVerificationWorklist.mockRejectedValue(
      new Error('Failed to load the verification worklist'),
    );
    renderList();

    await waitFor(() =>
      expect(
        screen.getByText('Failed to load the verification worklist.'),
      ).toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});

describe('empty state', () => {
  it('offers "Go to products" when no filters are active', async () => {
    getSpecVerificationWorklist.mockResolvedValue({
      data: [],
      pagination: { total: 0, page: 1, limit: 25 },
      summary: { total: 0, verified: 0, needs_reverify: 0, unverified: 0 },
      classes: [],
    });
    renderList();

    await waitFor(() =>
      expect(screen.getByText('Nothing to review here.')).toBeInTheDocument(),
    );
    expect(
      screen.getByText('No product code is waiting for verification.'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Go to products' }),
    ).toBeInTheDocument();
  });

  it('offers "Clear filters" instead when a filter is active from the URL', async () => {
    nav.params = new URLSearchParams({ query: 'nonexistent-code' });
    getSpecVerificationWorklist.mockResolvedValue({
      data: [],
      pagination: { total: 0, page: 1, limit: 25 },
      summary: { total: 0, verified: 0, needs_reverify: 0, unverified: 0 },
      classes: [],
    });
    renderList();

    await waitFor(() =>
      expect(
        screen.getByText('No product code matches these filters.'),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole('button', { name: 'Clear filters' }),
    ).toBeInTheDocument();
  });
});

describe('data state', () => {
  const ROWS = [
    row('WC100', 'needs_reverify'),
    row('WC200', 'unverified'),
    row('WC300', 'verified'),
  ];

  function mockWorklist(data = ROWS, total = data.length) {
    getSpecVerificationWorklist.mockResolvedValue({
      data,
      pagination: { total, page: 1, limit: 25 },
      summary: {
        total: 4812,
        verified: 3000,
        needs_reverify: 1000,
        unverified: 812,
      },
      classes: ['Bath Basin', 'Kitchen Sink'],
    });
  }

  it('renders all three verification pills and the progress line', async () => {
    mockWorklist();
    renderList();

    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());
    expect(screen.getByText('Needs re-verify')).toBeInTheDocument();
    expect(screen.getByText('Unverified')).toBeInTheDocument();
    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.getByTestId('verification-progress').textContent).toContain(
      'Verified 3,000 of 4,812 live codes',
    );
  });

  it('the needs-re-verify tooltip reads the diff entries as values, never [object Object]', async () => {
    // The wire shape of `invalidated_diff.changed`: each side is the stored ENTRY
    // (`{ value, unit? }`), or null when the key was absent on that side.
    mockWorklist([
      row('WC100', 'needs_reverify', {
        verification: {
          state: 'needs_reverify',
          verified_by_name: 'Jay Odoo',
          verified_at: '2026-08-01T09:00:00',
          invalidated_at: '2026-08-10T10:00:00',
          invalidated_reason: 'values_changed',
          invalidated_by_name: null,
          invalidated_diff: {
            changed: [
              {
                spec_key: 'material',
                was: { value: 'glass' },
                now: { value: 'ceramic' },
              },
              {
                spec_key: 'dim_height',
                was: { value: 770, unit: 'mm' },
                now: null,
              },
            ],
          },
        },
      }),
    ]);
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    const title =
      screen.getByText('Needs re-verify').getAttribute('title') ?? '';
    expect(title).not.toContain('[object Object]');
    expect(title).toContain('2 changed');
    expect(title).toContain('Material: Glass to Ceramic');
    expect(title).toContain('Height: 770 mm to nothing');
  });

  it('the per-row action follows the row state: Verify on unverified/needs_reverify, Unverify on verified', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    const rowWC100 = screen.getByText('WC100').closest('tr') as HTMLElement;
    const rowWC200 = screen.getByText('WC200').closest('tr') as HTMLElement;
    const rowWC300 = screen.getByText('WC300').closest('tr') as HTMLElement;

    expect(
      within(rowWC100).getByRole('button', { name: 'Verify' }),
    ).toBeInTheDocument();
    expect(
      within(rowWC200).getByRole('button', { name: 'Verify' }),
    ).toBeInTheDocument();
    expect(
      within(rowWC300).getByRole('button', { name: 'Unverify' }),
    ).toBeInTheDocument();
  });

  it('offers no Verify or Unverify to a user without master_data.products.edit', async () => {
    // The server refuses them anyway; showing the button would mean a 403 is the first
    // thing a reader learns. Same slug the Specifications tab gates its editors on.
    usePermissions.mockReturnValue({
      permissionSet: new Set(['master_data.products.view']),
    });
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    expect(
      screen.queryByRole('button', { name: 'Verify' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Unverify' }),
    ).not.toBeInTheDocument();

    // ... and neither does the bulk bar, once rows are selected.
    fireEvent.click(screen.getAllByRole('checkbox')[1]);
    await waitFor(() =>
      expect(screen.getByText('1 selected')).toBeInTheDocument(),
    );
    expect(
      screen.queryByRole('button', { name: 'Verify selected' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Unverify selected' }),
    ).not.toBeInTheDocument();
  });

  it('clicking a row navigates to the product Specifications tab, carrying this list back', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    fireEvent.click(screen.getByText('WC100'));

    // No new detail route, and `back` is the worklist URL plus the row being left, so
    // the trip out and home again costs the reviewer nothing.
    const pushed = String(nav.push.mock.calls[0][0]);
    expect(
      pushed.startsWith(
        '/master-data-management/products/id-WC100?tab=specifications&back=',
      ),
    ).toBe(true);
    const back = decodeURIComponent(pushed.split('&back=')[1]);
    expect(back.startsWith('/master-data-management/spec-verification?')).toBe(
      true,
    );
    expect(new URLSearchParams(back.split('?')[1]).get('focus')).toBe('WC100');
  });

  it('the Coverage cell opens only the keys that hold a value; the count carries the gap', async () => {
    mockWorklist([row('WC100', 'unverified')]);
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    const trigger = screen.getByRole('button', {
      name: 'Coverage: 2 of 3 applicable keys hold a value',
    });
    // Tabbing to it opens it, which is the same thing a click does here.
    fireEvent.focus(trigger);

    const list = await screen.findByRole('list');
    const entries = within(list)
      .getAllByRole('listitem')
      .map((li) => li.textContent);
    expect(entries).toEqual(['Material: Ceramic', 'Height: 770 mm']);

    // The blank key is not a row: how many are missing is what the header line says.
    expect(screen.queryByText(/Finish or colour/)).not.toBeInTheDocument();
    expect(screen.queryByText(/not set/)).not.toBeInTheDocument();
    expect(
      screen.getByText('2 of 3 applicable keys hold a value'),
    ).toBeInTheDocument();
  });

  it('the Coverage cell says nothing is set rather than listing blanks', async () => {
    const bare = row('WC100', 'unverified');
    bare.coverage = {
      have: 0,
      applicable: 2,
      items: [
        { spec_key: 'material', label: 'Material', value: null },
        { spec_key: 'finish', label: 'Finish or colour', value: null },
      ],
    };
    mockWorklist([bare]);
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    fireEvent.focus(
      screen.getByRole('button', {
        name: 'Coverage: 0 of 2 applicable keys hold a value',
      }),
    );

    expect(await screen.findByText('Nothing set yet')).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
    expect(screen.queryByText(/Material/)).not.toBeInTheDocument();
  });

  it('the row action does not itself navigate (stops propagation)', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC200')).toBeInTheDocument());
    verifySpecBulk.mockResolvedValue({
      results: [
        {
          product_code: 'WC200',
          outcome: 'verified',
          verification: row('WC200', 'verified').verification,
          values_hash: 'hash-WC200-v2',
        },
      ],
      counts: { verified: 1, skipped: 0 },
    });

    const rowWC200 = screen.getByText('WC200').closest('tr') as HTMLElement;
    fireEvent.click(within(rowWC200).getByRole('button', { name: 'Verify' }));

    await waitFor(() => expect(verifySpecBulk).toHaveBeenCalled());
    expect(nav.push).not.toHaveBeenCalled();
  });

  it('a per-row Verify is a bulk of one: it calls verify-bulk with exactly that code and its rendered hash', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC200')).toBeInTheDocument());
    verifySpecBulk.mockResolvedValue({
      results: [
        {
          product_code: 'WC200',
          outcome: 'verified',
          verification: row('WC200', 'verified').verification,
          values_hash: 'hash-WC200-v2',
        },
      ],
      counts: { verified: 1, skipped: 0 },
    });

    const rowWC200 = screen.getByText('WC200').closest('tr') as HTMLElement;
    fireEvent.click(within(rowWC200).getByRole('button', { name: 'Verify' }));

    await waitFor(() =>
      expect(verifySpecBulk).toHaveBeenCalledWith([
        { product_code: 'WC200', values_hash: 'hash-WC200' },
      ]),
    );
    // No confirmation dialog for the per-row action.
    expect(screen.queryByText('Confirm verify')).not.toBeInTheDocument();
  });

  it('a rejected per-row Verify surfaces as a toast, not an unhandled promise rejection', async () => {
    const unhandled: unknown[] = [];
    const onUnhandled = (reason: unknown) => {
      unhandled.push(reason);
    };
    process.on('unhandledRejection', onUnhandled);
    try {
      mockWorklist();
      renderList();
      await waitFor(() =>
        expect(screen.getByText('WC200')).toBeInTheDocument(),
      );
      verifySpecBulk.mockRejectedValue(new Error('Failed to verify'));

      const rowWC200 = screen.getByText('WC200').closest('tr') as HTMLElement;
      fireEvent.click(within(rowWC200).getByRole('button', { name: 'Verify' }));

      await waitFor(() => expect(verifySpecBulk).toHaveBeenCalled());
      const { toast } = await import('sonner');
      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith('Failed to verify'),
      );
      // Flush any rejection that escaped the handler.
      await new Promise((resolve) => setImmediate(resolve));

      expect(unhandled).toEqual([]);
      // The row was not patched: it still offers Verify.
      expect(
        within(rowWC200).getByRole('button', { name: 'Verify' }),
      ).toBeInTheDocument();
    } finally {
      process.off('unhandledRejection', onUnhandled);
    }
  });

  it('a row-level Unverify is confirmed first, with a count of one, and only then sent', async () => {
    // PRINCIPLES: confirm before every destructive OR detach action, never one-click.
    // Verify is not destructive and stays one-click; withdrawing a stamp is not.
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC300')).toBeInTheDocument());
    unverifySpecBulk.mockResolvedValue({
      results: [
        {
          product_code: 'WC300',
          outcome: 'unverified',
          verification: row('WC300', 'unverified').verification,
        },
      ],
      counts: { unverified: 1, no_change: 0 },
    });

    const rowWC300 = screen.getByText('WC300').closest('tr') as HTMLElement;
    fireEvent.click(within(rowWC300).getByRole('button', { name: 'Unverify' }));

    await waitFor(() =>
      expect(screen.getByText('Confirm unverify')).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/Withdraw the verification on 1 product code\?/),
    ).toBeInTheDocument();
    expect(unverifySpecBulk).not.toHaveBeenCalled();

    const dialog = screen.getByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Unverify' }));

    await waitFor(() =>
      expect(unverifySpecBulk).toHaveBeenCalledWith(['WC300']),
    );
  });

  it('cancelling the row-level Unverify confirmation sends nothing', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC300')).toBeInTheDocument());

    const rowWC300 = screen.getByText('WC300').closest('tr') as HTMLElement;
    fireEvent.click(within(rowWC300).getByRole('button', { name: 'Unverify' }));
    await waitFor(() =>
      expect(screen.getByText('Confirm unverify')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() =>
      expect(screen.queryByText('Confirm unverify')).not.toBeInTheDocument(),
    );
    expect(unverifySpecBulk).not.toHaveBeenCalled();
  });

  it('changing page clears the selection, so a bulk action can only ever send on-page codes', async () => {
    // The raw selection map is keyed on product_code and outlives the page it was
    // made on; the toolbar count would then disagree with what is actually sent.
    mockWorklist(ROWS, 60);
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    fireEvent.click(
      screen.getByRole('checkbox', { name: 'Select all rows on this page' }),
    );
    expect(screen.getByText('3 selected')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Go to next page' }));

    await waitFor(() =>
      expect(screen.queryByText('3 selected')).not.toBeInTheDocument(),
    );
    expect(
      screen.queryByRole('button', { name: /Verify selected/ }),
    ).not.toBeInTheDocument();
  });

  it('after a page change the bulk verify sends only the code selected on the new page', async () => {
    mockWorklist(ROWS, 60);
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());
    verifySpecBulk.mockResolvedValue({
      results: [
        {
          product_code: 'WC200',
          outcome: 'verified',
          verification: row('WC200', 'verified').verification,
          values_hash: 'hash-WC200-v2',
        },
      ],
      counts: { verified: 1, skipped: 0 },
    });

    fireEvent.click(
      screen.getByRole('checkbox', { name: 'Select all rows on this page' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Go to next page' }));
    await waitFor(() =>
      expect(screen.queryByText('3 selected')).not.toBeInTheDocument(),
    );
    // Page 2 is its own query, so the rows re-render once it resolves.
    await waitFor(() => expect(screen.getByText('WC200')).toBeInTheDocument());

    const rowWC200 = screen.getByText('WC200').closest('tr') as HTMLElement;
    fireEvent.click(
      within(rowWC200).getByRole('checkbox', { name: 'Select row' }),
    );
    fireEvent.click(screen.getByRole('button', { name: /Verify selected/ }));
    await waitFor(() =>
      expect(screen.getByText(/Verify 1 product code\?/)).toBeInTheDocument(),
    );
    const dialog = screen.getByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Verify' }));

    await waitFor(() =>
      expect(verifySpecBulk).toHaveBeenCalledWith([
        { product_code: 'WC200', values_hash: 'hash-WC200' },
      ]),
    );
  });

  it('select-all is page-scoped: no cross-page "select all matching" banner ever renders', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    fireEvent.click(
      screen.getByRole('checkbox', { name: 'Select all rows on this page' }),
    );

    expect(screen.getByText('3 selected')).toBeInTheDocument();
    expect(
      screen.queryByText(/select all .* records/i),
    ).not.toBeInTheDocument();
  });

  it('selecting rows shows both bulk actions in the strip', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    const rowWC100 = screen.getByText('WC100').closest('tr') as HTMLElement;
    fireEvent.click(
      within(rowWC100).getByRole('checkbox', { name: 'Select row' }),
    );

    expect(
      screen.getByRole('button', { name: /Verify selected/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Unverify selected/ }),
    ).toBeInTheDocument();
  });

  it('confirmation copy states the selected count', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    fireEvent.click(
      screen.getByRole('checkbox', { name: 'Select all rows on this page' }),
    );
    fireEvent.click(screen.getByRole('button', { name: /Verify selected/ }));

    await waitFor(() =>
      expect(screen.getByText('Confirm verify')).toBeInTheDocument(),
    );
    expect(screen.getByText(/Verify 3 product codes\?/)).toBeInTheDocument();
  });

  it('the confirmation pluralises properly: one selected code reads "1 product code"', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    const rowWC100 = screen.getByText('WC100').closest('tr') as HTMLElement;
    fireEvent.click(
      within(rowWC100).getByRole('checkbox', { name: 'Select row' }),
    );
    fireEvent.click(screen.getByRole('button', { name: /Verify selected/ }));

    await waitFor(() =>
      expect(screen.getByText(/Verify 1 product code\?/)).toBeInTheDocument(),
    );
  });

  it('the selection is written to the URL, so it survives opening a product and coming back', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    const rowWC100 = screen.getByText('WC100').closest('tr') as HTMLElement;
    fireEvent.click(
      within(rowWC100).getByRole('checkbox', { name: 'Select row' }),
    );

    await waitFor(() => {
      const urls = nav.replace.mock.calls.map((call) => String(call[0]));
      expect(urls.some((url) => url.includes('selected=WC100'))).toBe(true);
    });
  });

  it('a selection carried in the URL is restored, and is what a bulk action then sends', async () => {
    nav.params = new URLSearchParams({ selected: 'WC200' });
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC200')).toBeInTheDocument());

    const rowWC200 = screen.getByText('WC200').closest('tr') as HTMLElement;
    expect(
      within(rowWC200).getByRole('checkbox', { name: 'Select row' }),
    ).toBeChecked();
    expect(screen.getByText('1 selected')).toBeInTheDocument();

    verifySpecBulk.mockResolvedValue({
      results: [
        {
          product_code: 'WC200',
          outcome: 'verified',
          verification: row('WC200', 'verified').verification,
          values_hash: 'hash-WC200-v2',
        },
      ],
      counts: { verified: 1, skipped: 0 },
    });
    fireEvent.click(screen.getByRole('button', { name: /Verify selected/ }));
    await waitFor(() =>
      expect(screen.getByText(/Verify 1 product code\?/)).toBeInTheDocument(),
    );
    const dialog = screen.getByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Verify' }));

    await waitFor(() =>
      expect(verifySpecBulk).toHaveBeenCalledWith([
        { product_code: 'WC200', values_hash: 'hash-WC200' },
      ]),
    );
  });

  it('`focus` in the URL scrolls that row back into view, once', async () => {
    nav.params = new URLSearchParams({ focus: 'WC300' });
    const scrollIntoView = vi.fn();
    // jsdom implements no scrolling at all, so the component calls it optionally.
    Element.prototype.scrollIntoView = scrollIntoView;
    mockWorklist();
    renderList();

    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1));
    const target = scrollIntoView.mock.instances[0] as HTMLElement;
    expect(target.getAttribute('data-spec-code')).toBe('WC300');
  });

  it('a mixed bulk verify: acted row flips pill in place, skipped row (values moved) stays selected', async () => {
    const rowsWithSkip = [
      row('WC200', 'unverified'),
      row('WC400', 'unverified'),
    ];
    mockWorklist(rowsWithSkip);
    renderList();
    await waitFor(() => expect(screen.getByText('WC200')).toBeInTheDocument());

    verifySpecBulk.mockResolvedValue({
      results: [
        {
          product_code: 'WC200',
          outcome: 'verified',
          verification: row('WC200', 'verified').verification,
          values_hash: 'hash-WC200-v2',
        },
        { product_code: 'WC400', outcome: 'values_changed' },
      ],
      counts: { verified: 1, skipped: 1 },
    });

    fireEvent.click(
      screen.getByRole('checkbox', { name: 'Select all rows on this page' }),
    );
    fireEvent.click(screen.getByRole('button', { name: /Verify selected/ }));
    await waitFor(() =>
      expect(screen.getByText('Confirm verify')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() => expect(verifySpecBulk).toHaveBeenCalled());

    // Acted row flips to Unverify (now verified), in the SAME table position.
    await waitFor(() => {
      const codes = screen.getAllByRole('cell').length; // sanity: table still rendered
      expect(codes).toBeGreaterThan(0);
    });
    const rowWC200 = screen.getByText('WC200').closest('tr') as HTMLElement;
    const rowWC400 = screen.getByText('WC400').closest('tr') as HTMLElement;
    await waitFor(() =>
      expect(
        within(rowWC200).getByRole('button', { name: 'Unverify' }),
      ).toBeInTheDocument(),
    );

    // Row order in the DOM is unchanged: WC200 still precedes WC400.
    const allRows = screen
      .getAllByText(/^WC(200|400)$/)
      .map((el) => el.textContent);
    expect(allRows).toEqual(['WC200', 'WC400']);

    // The skipped row's own checkbox is still checked.
    expect(
      within(rowWC400).getByRole('checkbox', { name: 'Select row' }),
    ).toBeChecked();
    // The acted row's checkbox was released.
    expect(
      within(rowWC200).getByRole('checkbox', { name: 'Select row' }),
    ).not.toBeChecked();
  });
});
