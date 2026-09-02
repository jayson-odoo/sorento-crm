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

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), dismiss: vi.fn() },
}));

/**
 * Every countdown toast Unverify raised, in order, with the Cancel it was given -
 * the same capture `useDeferredRowAction.test.tsx` uses, since a row's countdown
 * lives in a toast (S6-07) that jsdom never actually paints.
 */
const raisedToasts: { id: string; subject: string; onCancel: () => void }[] = [];
const dismissDeferredToast = vi.fn();
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: (input: {
    pending: { id: string };
    subject: string;
    onCancel: () => void;
  }) => {
    raisedToasts.push({
      id: input.pending.id,
      subject: input.subject,
      onCancel: input.onCancel,
    });
    return `pending-action-${input.pending.id}`;
  },
  dismissDeferredToast: (...a: unknown[]) => dismissDeferredToast(...a),
}));

// `DataGrid` renders skeletons - and therefore no rows - until this answers, so the
// mock can reproduce the real sequence a resumed list goes through: data first, rows
// painted a beat later, and that second render happening inside the grid.
// `answersAfterMs` > 0 holds the grid on skeletons for that long, past the point the
// worklist data itself lands, which is the real sequence a resumed list goes through.
const prefs = vi.hoisted(() => ({ answersAfterMs: 0 }));
vi.mock(
  '@/lib/listing-column-preferences/useListingColumnPreferences',
  async () => {
    const react = await import('react');
    return {
      useListingColumnPreferences: () => {
        const [isLoading, setIsLoading] = react.useState(
          prefs.answersAfterMs > 0,
        );
        react.useEffect(() => {
          if (!isLoading) return;
          const timer = setTimeout(
            () => setIsLoading(false),
            prefs.answersAfterMs,
          );
          return () => clearTimeout(timer);
        }, [isLoading]);
        return { resetToDefaults: async () => {}, isLoading };
      },
    };
  },
);

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

// Unverify (row and bulk) runs through the deferred-action engine now (D7, D8,
// AC-F.1) - the same three routes every other deferred delete/withdraw goes
// through, mocked the same way `PromotionTypesList.test.tsx` mocks them.
const createPendingAction = vi.fn();
const cancelPendingAction = vi.fn();
const getCurrentPendingAction = vi.fn();
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...a: unknown[]) => createPendingAction(...a),
  cancelPendingAction: (...a: unknown[]) => cancelPendingAction(...a),
  getCurrentPendingAction: (...a: unknown[]) => getCurrentPendingAction(...a),
}));

import SpecVerificationList from './SpecVerificationList';
import { pendingEntityStore } from '@/lib/pending-entity-store';
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

/** Returns the render result plus the QueryClient, so a test can drive a commit
 * directly (`client.refetchQueries`) rather than waiting out the real 500ms poll. */
function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={client}>
      <SpecVerificationList />
    </QueryClientProvider>,
  );
  return { ...utils, client };
}

/** A naive-UTC timestamp `offsetMs` from now, the way the backend writes them. */
function serverTime(offsetMs: number): string {
  return new Date(Date.now() + offsetMs).toISOString().replace(/\.\d+Z$/, '');
}

beforeEach(() => {
  vi.clearAllMocks();
  prefs.answersAfterMs = 0;
  nav.params = new URLSearchParams();
  usePermissions.mockReturnValue({
    permissionSet: new Set(['master_data.products.edit']),
  });
  // Module-level state is per TAB, and each test is a fresh tab: a row dimmed by
  // one test would otherwise still read dimmed in the next.
  pendingEntityStore.reset();
  raisedToasts.length = 0;
  createPendingAction.mockResolvedValue({
    id: 'pa-1',
    action_key: 'spec_verification.unverify',
    entity_type: 'spec_verification',
    entity_id: 'WC300',
    commit_at: serverTime(5_000),
    window_seconds: 5,
  });
  cancelPendingAction.mockResolvedValue(undefined);
  // Mirrors what a real server answers with while the window is still open (the
  // same row `createPendingAction` just parked) - a bare `pending: null` here would
  // read as an already-settled action the moment the row's own poll asks, which
  // no server actually says while the countdown is still running.
  getCurrentPendingAction.mockResolvedValue({
    pending: {
      id: 'pa-1',
      action_key: 'spec_verification.unverify',
      entity_type: 'spec_verification',
      entity_id: 'WC300',
      commit_at: serverTime(5_000),
      window_seconds: 5,
    },
    last_outcome: null,
  });
});

afterEach(() => cleanup());

describe('loading state', () => {
  // The shared ListSearchInput is never disabled while a query is in flight -
  // each keystroke changes the query key, so the box is pending for most of
  // the typing, and disabling it on that flip drops the rest of the word.
  it('shows the progress-line skeleton while the worklist loads, search box usable', () => {
    getSpecVerificationWorklist.mockReturnValue(new Promise(() => {})); // never resolves
    renderList();

    expect(
      screen.queryByTestId('verification-progress')?.textContent ?? '',
    ).not.toContain('Verified');
    expect(screen.getByPlaceholderText('Search code or name')).not.toBeDisabled();
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

  it('the Coverage cell opens on a tap, not only on hover', async () => {
    // A touch device reports no hover and never focuses on tap, so the uncontrolled
    // HoverCard gave a phone reviewer the count and nothing else.
    mockWorklist([row('WC100', 'unverified')]);
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    const trigger = screen.getByRole('button', {
      name: 'Coverage: 2 of 3 applicable keys hold a value',
    });
    expect(trigger).toHaveAttribute(
      'title',
      '2 of 3 applicable keys hold a value',
    );

    fireEvent.click(trigger);

    const list = await screen.findByRole('list');
    expect(
      within(list)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(['Material: Ceramic', 'Height: 770 mm']);
    // ... and the row itself did not navigate underneath it.
    expect(nav.push).not.toHaveBeenCalled();
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

  it('the Coverage cell shows a warning pill when open_exceptions is set, and nothing when it is zero (AC-F.4)', async () => {
    mockWorklist([
      row('WC100', 'unverified', { open_exceptions: 0 }),
      row('WC200', 'unverified', { open_exceptions: 2 }),
    ]);
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());

    const rowWC100 = screen.getByText('WC100').closest('tr') as HTMLElement;
    const rowWC200 = screen.getByText('WC200').closest('tr') as HTMLElement;

    expect(within(rowWC100).queryByText(/need a human/)).not.toBeInTheDocument();
    expect(within(rowWC200).getByText('2 need a human')).toBeInTheDocument();

    // The hover card carries the same count - the payload has no reasons to list -
    // portaled outside the row, so it is a SECOND instance of the same sentence.
    fireEvent.focus(
      within(rowWC200).getByRole('button', { name: /^Coverage:/ }),
    );
    await waitFor(() =>
      expect(screen.getAllByText('2 need a human').length).toBeGreaterThanOrEqual(2),
    );
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
      const { toast } = await import('@/lib/toast');
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

  it('a row-level Unverify parks a deferred action, with no dialog in the way (AC-F.1)', async () => {
    // D7, D8: Unverify no longer confirms - the first press IS the action, and the
    // countdown travels to a toast while the row dims (S6-07, a list row has
    // nowhere to put an inline one). Verify is unaffected (it never confirmed
    // row-level either).
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC300')).toBeInTheDocument());

    const rowWC300 = screen.getByText('WC300').closest('tr') as HTMLElement;
    fireEvent.click(within(rowWC300).getByRole('button', { name: 'Unverify' }));

    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'spec_verification.unverify',
          entityType: 'spec_verification',
          entityId: 'WC300',
        }),
      ),
    );
    expect(screen.queryByText('Confirm unverify')).not.toBeInTheDocument();
    expect(unverifySpecBulk).not.toHaveBeenCalled();
    await waitFor(() => expect(raisedToasts).toHaveLength(1));
    expect(raisedToasts[0].subject).toBe('WC300');
    await waitFor(() =>
      expect(rowWC300).toHaveAttribute('data-pending', 'true'),
    );
  });

  it('the row-level Unverify countdown can be cancelled from its toast, and nothing is sent', async () => {
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC300')).toBeInTheDocument());

    const rowWC300 = screen.getByText('WC300').closest('tr') as HTMLElement;
    fireEvent.click(within(rowWC300).getByRole('button', { name: 'Unverify' }));
    await waitFor(() => expect(raisedToasts).toHaveLength(1));

    raisedToasts[0].onCancel();

    await waitFor(() => expect(cancelPendingAction).toHaveBeenCalledWith('pa-1'));
    await waitFor(() =>
      expect(rowWC300).not.toHaveAttribute('data-pending', 'true'),
    );
    expect(unverifySpecBulk).not.toHaveBeenCalled();
  });

  it('a committed row-level Unverify refetches the worklist (AC-F.2)', async () => {
    // The server withdraws the stamp itself (`spec_verification.unverify`, a
    // registered record action, `record_actions.py`) - this proves the row's own
    // pending-action watch learns the commit and the list catches up.
    mockWorklist();
    const { client } = renderList();
    await waitFor(() => expect(screen.getByText('WC300')).toBeInTheDocument());

    const rowWC300 = screen.getByText('WC300').closest('tr') as HTMLElement;
    fireEvent.click(within(rowWC300).getByRole('button', { name: 'Unverify' }));
    await waitFor(() =>
      expect(rowWC300).toHaveAttribute('data-pending', 'true'),
    );

    getSpecVerificationWorklist.mockClear();
    getCurrentPendingAction.mockResolvedValue({
      pending: null,
      last_outcome: {
        id: 'pa-1',
        action_key: 'spec_verification.unverify',
        status: 'committed',
        error_text: null,
        ended_at: serverTime(0),
      },
    });
    await client.refetchQueries({ queryKey: ['pending-action-current'] });

    // The row un-dims once the window has closed, and the worklist is asked for
    // again so the row's own pill catches up.
    await waitFor(() =>
      expect(rowWC300).not.toHaveAttribute('data-pending', 'true'),
    );
    await waitFor(() =>
      expect(getSpecVerificationWorklist).toHaveBeenCalled(),
    );
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

  it('`focus` still scrolls when the grid paints its rows a render late', async () => {
    // The regression: the restore spent its one shot on the render where the data had
    // arrived but the grid was still showing skeletons, so the reviewer came back to
    // the top of the list rather than to the row they left from.
    // The grid answers its column preferences AFTER the rows are in state, so there is
    // a render with data and no row in the DOM - and the render that finally paints it
    // happens inside the grid, where this component has nothing to re-run on.
    prefs.answersAfterMs = 50;
    nav.params = new URLSearchParams({ focus: 'WC300' });
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    mockWorklist();
    renderList();

    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1));
    expect(
      (scrollIntoView.mock.instances[0] as HTMLElement).getAttribute(
        'data-spec-code',
      ),
    ).toBe('WC300');
  });

  it('changing a filter clears the selection and drops it from the URL', async () => {
    // Same rule as changing page: a code the filtered list no longer shows must not
    // ride a bulk action, and the URL must not carry it back on a refresh either. The
    // selection is seeded from the URL with an off-page code, which is how it outlives
    // a page in the first place - and, since it selects no visible row, the toolbar
    // still shows the search box rather than the bulk strip.
    nav.params = new URLSearchParams({ selected: 'WC999' });
    mockWorklist();
    renderList();
    await waitFor(() => expect(screen.getByText('WC100')).toBeInTheDocument());
    await waitFor(() =>
      expect(
        nav.replace.mock.calls.some((call) =>
          String(call[0]).includes('selected=WC999'),
        ),
      ).toBe(true),
    );

    const search = screen.getByPlaceholderText('Search code or name');
    fireEvent.change(search, { target: { value: 'WC1' } });
    fireEvent.keyDown(search, { key: 'Enter' });

    await waitFor(() => {
      const lastUrl = String(
        nav.replace.mock.calls[nav.replace.mock.calls.length - 1][0],
      );
      expect(lastUrl).toContain('query=WC1');
      expect(lastUrl).not.toContain('selected=');
    });
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
