/**
 * FILTER-MULTISELECT PR4b: the Packing lists Region filter takes both regions (OR), comma-joined to the
 * data hook and in the page URL. An older link holding one region reads back as a one-value filter.
 * Harness mirrors PackingListsList.regionFilter.test.tsx.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
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
  usePathname: () => '/procurement-management/packing-lists',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/upload-activity', () => ({ useUploadManager: () => ({ startSession: vi.fn() }) }));
const usePackingLists = vi.hoisted(() => vi.fn());
vi.mock('../hooks/usePackingLists', () => ({
  usePackingLists: (...a: unknown[]) => usePackingLists(...a),
  useBulkDeletePackingLists: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeletePackingList: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('../services/packingListService', () => ({ getLatestContainerStatusDocument: vi.fn() }));
vi.mock('@/app/(protected)/scm/services/fulfilmentService', () => ({
  previewSupplierDocuments: vi.fn(), applySupplierDocuments: vi.fn(), getFulfilmentSuppliers: vi.fn(async () => []),
}));
vi.mock('@/app/(protected)/resource-management/attachments/hooks/useAttachments', () => ({
  useAttachmentTypesList: () => ({ data: [], isLoading: false }),
}));
vi.mock('@/app/(protected)/resource-management/attachments/components/AttachmentUploadDialog', () => ({ default: () => null }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
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

vi.mock('@/hooks/usePermissions', () => ({ useHasAnyPermission: () => true }));
vi.mock('@/hooks/useTenantModules', () => ({
  useTenantModules: () => ({ enabledModuleKeys: new Set(['procurement', 'scm']), isLoading: false }),
}));
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

import PackingListsList from './PackingListsList';

const ROW = {
  id: 'pl-1', shipment_number: 'ZZT-PL-0001', shipping_container_number: 'TEMU1234567',
  supplier: { id: 'sup-1', supplier_code: 'SUP1', supplier_name: 'Acme Sanitary' }, shipment_date: '2026-08-01',
  estimated_arrival_date: null, shipment_status: 'in_transit', total_items_shipped: 100,
  created_at: '2026-08-01T00:00:00Z', regions: ['west'],
};
const lastParams = () => usePackingLists.mock.calls[usePackingLists.mock.calls.length - 1][0] as Record<string, unknown>;
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
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PackingListsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  url.search = '';
  usePackingLists.mockReturnValue({
    data: { data: [ROW], pagination: { page: 1, total: 1 } },
    isLoading: false, isFetching: false, isPlaceholderData: false, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

describe('Packing lists - multi Region filter', () => {
  it('Region is a multi control', async () => {
    renderList();
    expect((await box('west')).hasAttribute('multiple')).toBe(true);
  });

  it('both regions reach the hook as a set of two and the badge counts one filter', async () => {
    const user = userEvent.setup();
    renderList();
    await user.selectOptions(await box('west'), ['west', 'east']);
    await waitFor(() => expect(setOf(lastParams().region)).toEqual(['east', 'west']));
    expect(within(filtersButton()).getByText('1')).toBeInTheDocument();
  });

  it('one region still reaches the hook as one value', async () => {
    const user = userEvent.setup();
    renderList();
    await user.selectOptions(await box('west'), ['east']);
    await waitFor(() => expect(setOf(lastParams().region)).toEqual(['east']));
  });

  it('unticking every region drops the filter', async () => {
    url.search = 'region=west%2Ceast';
    const user = userEvent.setup();
    renderList();
    await user.deselectOptions(await box('west'), ['west', 'east']);
    await waitFor(() => expect(setOf(lastParams().region)).toEqual([]));
  });

  it('a link with both regions restores the control and the request', async () => {
    url.search = 'region=west%2Ceast';
    renderList();
    await waitFor(() => expect(setOf(lastParams().region)).toEqual(['east', 'west']));
    expect(selected(await box('west'))).toEqual(['east', 'west']);
  });

  it('an older link with one region reads back as a one-value filter', async () => {
    url.search = 'region=east';
    renderList();
    await waitFor(() => expect(setOf(lastParams().region)).toEqual(['east']));
    expect(selected(await box('west'))).toEqual(['east']);
  });
});
