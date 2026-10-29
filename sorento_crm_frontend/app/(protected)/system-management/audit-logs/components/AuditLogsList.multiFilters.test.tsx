/**
 * FILTER-MULTISELECT PR2: the Audit logs list's Entity type, Action and User filters take several
 * values (OR within a filter, AND across), comma-joined to the data hook. The "All" placeholders are
 * never values. Harness mirrors AuditLogsList.dateFilter.test.tsx.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AuditLogsList from './AuditLogsList';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/system-management/audit-logs',
  useSearchParams: () => ({ get: () => null }),
}));
const useAuditLogs = vi.fn();
vi.mock('../hooks/useAuditLogs', () => ({ useAuditLogs: (...a: unknown[]) => useAuditLogs(...a) }));
vi.mock('@/services/userSelectService', () => ({
  getUsersSelect: vi.fn(async () => [
    { id: 'u-ann', name: 'Ann Lee', email: 'ann@e.com' },
    { id: 'u-ben', name: 'Ben Lim', email: 'ben@e.com' },
  ]),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

const lastArgs = () => {
  const calls = useAuditLogs.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
};
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

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
  useAuditLogs.mockReset();
  useAuditLogs.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true },
    isLoading: false, isError: false, error: null, refetch: vi.fn(), isFetching: false,
  });
});
afterEach(() => cleanup());

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AuditLogsList />
    </QueryClientProvider>,
  );
  await user.click(await screen.findByRole('button', { name: /^filters/i }));
}

describe('Audit logs - multi Entity type, Action and User filters', () => {
  it('are three multi controls, Entity type then Action then User', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(3);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two entity types go to the hook comma-joined, never with the All placeholder', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const [entity] = await screen.findAllByRole('listbox');
    await user.selectOptions(entity, ['product', 'complaint']);
    await waitFor(() => expect(lastArgs().entity_type).toBe('product,complaint'));
    expect(String(lastArgs().entity_type)).not.toContain('__all__');
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('two actions go to the hook comma-joined, never with the All placeholder', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await user.selectOptions(boxes[1], ['INSERT', 'DELETE']);
    await waitFor(() => expect(lastArgs().action).toBe('INSERT,DELETE'));
    expect(String(lastArgs().action)).not.toContain('__all__');
  });

  it('two users go to the hook comma-joined', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await waitFor(() => expect((boxes[2] as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(boxes[2], ['u-ann', 'u-ben']);
    await waitFor(() => expect(lastArgs().user_id).toBe('u-ann,u-ben'));
  });

  it('the filters AND across each other', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await waitFor(() => expect((boxes[2] as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(boxes[0], ['product', 'complaint']);
    await user.selectOptions(boxes[1], ['UPDATE']);
    await user.selectOptions(boxes[2], ['u-ann', 'u-ben']);
    await waitFor(() =>
      expect(lastArgs()).toMatchObject({
        entity_type: 'product,complaint', action: 'UPDATE', user_id: 'u-ann,u-ben',
      }),
    );
  });
});
