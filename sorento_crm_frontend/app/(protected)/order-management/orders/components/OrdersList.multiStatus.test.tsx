/**
 * FILTER-MULTISELECT PR3: the Delivery orders list's Status filter takes several values (OR within the
 * filter), comma-joined to the data hook as `order_status_id`. It is URL-persisted, so a comma-joined
 * link and an older single-value link both read back. Harness mirrors OrdersList.branch.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import OrdersList from './OrdersList';

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(url.search),
  usePathname: () => '/order-management/orders',
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async (listingKey: string) => ({ listing_key: listingKey, config: null })),
  upsertUserListColumnConfig: vi.fn(async (listingKey: string, config: unknown) => ({ listing_key: listingKey, config })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));
const useOrders = vi.fn();
vi.mock('../hooks/useOrders', () => ({ useOrders: (...a: unknown[]) => useOrders(...a) }));
vi.mock('../../shared/hooks/use-order-status-select-query', () => ({
  useOrderStatusSelectQuery: () => ({
    data: [
      { id: 'st-new', status_name: 'ZZT New' },
      { id: 'st-proc', status_name: 'ZZT Processing' },
      { id: 'st-done', status_name: 'ZZT Delivered' },
    ],
  }),
}));
vi.mock('../actions', () => ({ OrderRowActions: () => null }));
vi.mock('@/components/upload-activity', () => ({ useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }) }));
vi.mock('@/hooks/useDeferredBulkAction', () => ({ useDeferredBulkAction: () => ({ start: vi.fn(), pending: false }) }));
vi.mock('@/lib/pending-entity-store', () => ({
  pendingEntityKey: (t: string, id: string) => `${t}:${id}`,
  usePendingEntityKeys: () => new Set<string>(),
}));
vi.mock('@/app/(protected)/system-management/import-jobs/autocount-pull/hooks/useAutocountPull', () => ({
  useAutocountPullAction: () => ({ label: 'Pull from AutoCount', onClick: vi.fn(), disabled: false }),
}));
vi.mock('@/app/(protected)/system-management/import-jobs/autocount-pull/components/PullScopeDialog', () => ({
  PullScopeDialog: () => null,
}));
vi.mock('@/components/template/TemplateUploadDialog', () => ({ TemplateUploadDialog: () => null }));
vi.mock('./OrderTrackingUploadDialog', () => ({ OrderTrackingUploadDialog: () => null }));
vi.mock('./OrderLinesImportDialog', () => ({ OrderLinesImportDialog: () => null }));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('').then(setLoaded);
    }, [fetchOptions]);
    return (
      <select multiple aria-label={placeholder ?? 'multi'} value={value}
        onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {(fetchOptions ? loaded : (options ?? [])).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  };
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

/** The multi control that offers this option text. */
const boxWith = async (option: string) => {
  const boxes = await screen.findAllByRole('listbox');
  const found = boxes.find((b) => within(b).queryByText(option));
  if (!found) throw new Error(`no multi control offers ${option}`);
  return found as HTMLSelectElement;
};
const asList = (v: unknown): string[] =>
  v == null || v === '' ? [] : Array.isArray(v) ? (v as string[]) : String(v).split(',');
const lastArgs = () => {
  const calls = useOrders.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
};

beforeEach(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
  url.search = '';
  useOrders.mockReset();
  useOrders.mockReturnValue({
    data: { data: [{ id: 'o-1', order_number: 'ZZT-DO-1' }], pagination: { total: 1, page: 1, limit: 50, pages: 1 } },
    isLoading: false, isPlaceholderData: false, isError: false, error: null, refetch: vi.fn(), isFetching: false,
  });
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrdersList />
    </QueryClientProvider>,
  );
}

describe('Delivery orders - multi Status filter', () => {
  it('is a multi control', async () => {
    renderIt();
    expect((await boxWith('ZZT Delivered')).hasAttribute('multiple')).toBe(true);
  });

  it('two statuses go to the hook comma-joined, never with the All placeholder', async () => {
    const user = userEvent.setup();
    renderIt();
    await user.selectOptions(await boxWith('ZZT Delivered'), ['st-new', 'st-done']);
    await waitFor(() => expect(asList(lastArgs().order_status_id)).toEqual(['st-new', 'st-done']));
    expect(asList(lastArgs().order_status_id)).not.toContain('all');
  });

  it('a comma-joined link reads back into the filter', async () => {
    url.search = 'order_status_id=st-new%2Cst-done';
    renderIt();
    await waitFor(() => expect(asList(lastArgs().order_status_id)).toEqual(['st-new', 'st-done']));
  });

  it('an older link with one status reads back as a one-value filter (guard)', async () => {
    url.search = 'order_status_id=st-proc';
    renderIt();
    await waitFor(() => expect(asList(lastArgs().order_status_id)).toEqual(['st-proc']));
  });
});
