/**
 * FILTER-MULTISELECT PR3: the Billing documents list's Status, Customer and Agent filters take several
 * values (OR within a filter, AND across); Type already did. Each reaches the data hook as a list or a
 * comma-joined string; either reads the same here.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const useBillingDocumentsQuery = vi.fn();
vi.mock('../hooks/useBillingDocuments', () => ({
  useBillingDocumentsQuery: (...a: unknown[]) => useBillingDocumentsQuery(...a),
  useBillingAgentOptions: () => ({
    data: [{ value: 'AG1', label: 'ZZT Ann' }, { value: 'AG2', label: 'ZZT Ben' }, { value: 'AG3', label: 'ZZT Cat' }],
    isError: false, refetch: vi.fn(),
  }),
  useCanExportBilling: () => false,
  useCanViewOutstanding: () => false,
}));
vi.mock('../services/billingDocumentService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/billingDocumentService')>();
  return {
    ...actual,
    searchBillingCustomerOptions: vi.fn(async () => [
      { value: 'cust-1', label: 'ZZT Cust One' }, { value: 'cust-2', label: 'ZZT Cust Two' },
    ]),
  };
});
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/finance/billing-documents',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/common/PageHeader', () => ({ PageHeader: ({ title }: { title: string }) => <h1>{title}</h1> }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
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

import BillingDocumentsView from './BillingDocumentsView';

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
  const calls = useBillingDocumentsQuery.mock.calls;
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
  useBillingDocumentsQuery.mockReset();
  useBillingDocumentsQuery.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
    isLoading: false, isFetching: false, isPlaceholderData: false, isError: false, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BillingDocumentsView />
    </QueryClientProvider>,
  );
}

describe('Billing documents - multi Status, Customer and Agent filters', () => {
  it('Type, Status, Customer and Agent are all multi controls', async () => {
    renderIt();
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(4);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('both statuses reach the hook', async () => {
    const user = userEvent.setup();
    renderIt();
    await user.selectOptions(await boxWith('Cancelled'), ['posted', 'cancelled']);
    await waitFor(() => expect(asList(lastArgs().status)).toEqual(['posted', 'cancelled']));
  });

  it('two customers reach the hook', async () => {
    const user = userEvent.setup();
    renderIt();
    const box = await boxWith('ZZT Cust Two');
    await user.selectOptions(box, ['cust-1', 'cust-2']);
    await waitFor(() => expect(asList(lastArgs().customerId)).toEqual(['cust-1', 'cust-2']));
  });

  it('two agents reach the hook', async () => {
    const user = userEvent.setup();
    renderIt();
    await user.selectOptions(await boxWith('ZZT Cat'), ['AG1', 'AG3']);
    await waitFor(() => expect(asList(lastArgs().agentCode)).toEqual(['AG1', 'AG3']));
  });

  it('the filters AND across each other', async () => {
    const user = userEvent.setup();
    renderIt();
    await user.selectOptions(await boxWith('ZZT Cat'), ['AG1', 'AG3']);
    await user.selectOptions(await boxWith('ZZT Cust Two'), ['cust-2']);
    await waitFor(() => {
      expect(asList(lastArgs().agentCode)).toEqual(['AG1', 'AG3']);
      expect(asList(lastArgs().customerId)).toEqual(['cust-2']);
    });
  });
});
