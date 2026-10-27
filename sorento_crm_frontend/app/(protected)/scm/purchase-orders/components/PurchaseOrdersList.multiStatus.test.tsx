/**
 * FILTER-MULTISELECT PR5: the Purchase orders list's Status filter takes several statuses (OR within the
 * filter), comma-joined to the data hook and in the page URL. An older link holding one status reads
 * back as a one-value filter. Harness mirrors PurchaseOrdersList.test.tsx (dropdown menu inline).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/purchase-orders',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
type MenuProps = { children?: React.ReactNode; onClick?: () => void; disabled?: boolean };
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: MenuProps) => <>{children}</>,
  DropdownMenuContent: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick, disabled }: MenuProps) => (
    <button type="button" onClick={onClick} disabled={disabled}>{children}</button>
  ),
  DropdownMenuCheckboxItem: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuGroup: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuPortal: ({ children }: MenuProps) => <>{children}</>,
  DropdownMenuSub: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuSubContent: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuSubTrigger: ({ children }: MenuProps) => <div>{children}</div>,
}));

const usePurchaseOrders = vi.hoisted(() => vi.fn());
vi.mock('../../hooks/usePurchaseOrders', () => ({ usePurchaseOrders: (...a: unknown[]) => usePurchaseOrders(...a) }));
vi.mock('../../hooks/usePurchaseOrderActions', () => ({
  usePurchaseOrderActions: () => ({
    confirm: { mutateAsync: vi.fn(), isPending: false },
    createGr: { mutateAsync: vi.fn(), isPending: false },
    bulkDelete: { mutateAsync: vi.fn(), isPending: false },
  }),
}));
vi.mock('../../reorder/components/OutstandingUploadDialog', () => ({ OutstandingUploadDialog: () => null }));
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

import PurchaseOrdersList from './PurchaseOrdersList';

const ROW = {
  id: 'po-1', po_number: 'ZZT-PO-0001', supplier_code: 'SUP-ACME', supplier_name: 'Acme Sanitary', warehouse_code: 'WH-KL',
  warehouse_name: 'Kuala Lumpur DC', status: 'draft_recommendation', order_date: '2026-07-16', expected_date: null,
  total_qty: 320, line_count: 1, lines: [], created_at: '2026-07-16T00:00:00',
};
const lastParams = () => usePurchaseOrders.mock.calls[usePurchaseOrders.mock.calls.length - 1][0] as Record<string, unknown>;
const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const boxesWith = (value: string) =>
  screen.queryAllByRole('listbox').filter(
    (el) => el.hasAttribute('multiple') && el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
async function box(value: string) {
  await waitFor(() => {
    if (!boxesWith(value).length) throw new Error(`no multi control offering option "${value}"`);
  });
  return boxesWith(value)[0];
}
const selected = (el: HTMLSelectElement) => Array.from(el.selectedOptions, (o) => o.value).sort();

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseOrdersList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  url.search = '';
  usePurchaseOrders.mockReturnValue({
    data: { data: [ROW], pagination: { page: 1, total: 1 } },
    isLoading: false, isFetching: false, isPlaceholderData: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

describe('Purchase orders - multi Status filter', () => {
  it('Status is a multi control', async () => {
    renderList();
    expect((await box('cancelled')).hasAttribute('multiple')).toBe(true);
  });

  it('two statuses reach the hook as a set of two', async () => {
    const user = userEvent.setup();
    renderList();
    await user.selectOptions(await box('cancelled'), ['draft_recommendation', 'cancelled']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['cancelled', 'draft_recommendation']));
  });

  it('the All statuses sentinel is never sent', async () => {
    renderList();
    await box('cancelled');
    expect(setOf(lastParams().status)).toEqual([]);
  });

  it('unticking every status drops the filter', async () => {
    url.search = 'status=draft_recommendation%2Ccancelled';
    const user = userEvent.setup();
    renderList();
    await user.deselectOptions(await box('cancelled'), ['draft_recommendation', 'cancelled']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual([]));
  });

  it('a link with several statuses restores the control and the request', async () => {
    url.search = 'status=draft_recommendation%2Ccancelled';
    renderList();
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['cancelled', 'draft_recommendation']));
    expect(selected(await box('cancelled'))).toEqual(['cancelled', 'draft_recommendation']);
  });

  it('an older link with one status reads back as a one-value filter', async () => {
    url.search = 'status=cancelled';
    renderList();
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['cancelled']));
    expect(selected(await box('cancelled'))).toEqual(['cancelled']);
  });
});
