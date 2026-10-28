/**
 * FILTER-MULTISELECT PR3: the Opportunities list's Stage, Agent and Customer filters take several
 * values (OR within a filter, AND across). Each reaches the data hook as a list or a comma-joined
 * string; either reads the same here. Harness mirrors SalesOpportunitiesView.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/sales/opportunities',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/common/PageHeader', () => ({ PageHeader: ({ title }: { title: string }) => <h1>{title}</h1> }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
const hooks = vi.hoisted(() => ({
  useSalesOpportunities: vi.fn(),
  useSalesOpportunityMeta: vi.fn(),
  useSalesOpportunityAgentOptions: vi.fn(),
}));
vi.mock('../hooks/useSalesOpportunities', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useSalesOpportunities')>();
  return {
    ...actual,
    useSalesOpportunities: (...a: unknown[]) => hooks.useSalesOpportunities(...a),
    useSalesOpportunityMeta: (...a: unknown[]) => hooks.useSalesOpportunityMeta(...a),
    useSalesOpportunityAgentOptions: (...a: unknown[]) => hooks.useSalesOpportunityAgentOptions(...a),
  };
});
vi.mock('../services/salesOpportunityService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/salesOpportunityService')>();
  return {
    ...actual,
    getSalesOpportunityCustomerOptions: vi.fn(async () => ({
      items: [
        { customer_id: 'cust-1', customer_code: 'C1', customer_name: 'ZZT One' },
        { customer_id: 'cust-2', customer_code: 'C2', customer_name: 'ZZT Two' },
      ],
    })),
  };
});
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

import SalesOpportunitiesView from './SalesOpportunitiesView';

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
  const calls = hooks.useSalesOpportunities.mock.calls;
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
  vi.clearAllMocks();
  hooks.useSalesOpportunities.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
    isLoading: false, isFetching: false, isPlaceholderData: false, isError: false, refetch: vi.fn(),
  });
  hooks.useSalesOpportunityMeta.mockReturnValue({
    data: { stages: [{ id: 'st-1', label: 'ZZT Lead' }, { id: 'st-2', label: 'ZZT Quote' }, { id: 'st-3', label: 'ZZT Won' }] },
  });
  hooks.useSalesOpportunityAgentOptions.mockReturnValue({
    data: [{ id: 'ag-1', label: 'ZZT Ann' }, { id: 'ag-2', label: 'ZZT Ben' }],
  });
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesOpportunitiesView />
    </QueryClientProvider>,
  );
}

describe('Opportunities - multi Stage, Agent and Customer filters', () => {
  it('are three multi controls', async () => {
    renderIt();
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(3);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two stages reach the hook', async () => {
    const user = userEvent.setup();
    renderIt();
    await user.selectOptions(await boxWith('ZZT Won'), ['st-1', 'st-3']);
    await waitFor(() => expect(asList(lastArgs().statusId)).toEqual(['st-1', 'st-3']));
  });

  it('two agents reach the hook', async () => {
    const user = userEvent.setup();
    renderIt();
    await user.selectOptions(await boxWith('ZZT Ben'), ['ag-1', 'ag-2']);
    await waitFor(() => expect(asList(lastArgs().salesAgentId)).toEqual(['ag-1', 'ag-2']));
  });

  it('two customers reach the hook', async () => {
    const user = userEvent.setup();
    renderIt();
    const box = await boxWith('C2 - ZZT Two');
    await user.selectOptions(box, ['cust-1', 'cust-2']);
    await waitFor(() => expect(asList(lastArgs().customerId)).toEqual(['cust-1', 'cust-2']));
  });

  it('the filters AND across each other', async () => {
    const user = userEvent.setup();
    renderIt();
    await user.selectOptions(await boxWith('ZZT Won'), ['st-1', 'st-2']);
    await user.selectOptions(await boxWith('ZZT Ben'), ['ag-2']);
    await waitFor(() => {
      expect(asList(lastArgs().statusId)).toEqual(['st-1', 'st-2']);
      expect(asList(lastArgs().salesAgentId)).toEqual(['ag-2']);
    });
  });
});
