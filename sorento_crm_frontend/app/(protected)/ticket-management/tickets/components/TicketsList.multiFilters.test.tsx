/**
 * FILTER-MULTISELECT PR3: the Tickets list's Status, Priority, Category and Source filters take several
 * values (OR within a filter, AND across). Each reaches the list service as a list or a comma-joined
 * string; either reads the same here. Harness mirrors TicketsList.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/ticket-management/tickets',
  useSearchParams: () => new URLSearchParams(''),
}));
const getTickets = vi.fn();
vi.mock('../services/ticketService', () => ({
  getTickets: (...a: unknown[]) => getTickets(...a),
  bulkDeleteTickets: vi.fn(async () => {}),
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

import TicketsList from './TicketsList';

const asList = (v: unknown): string[] =>
  v == null || v === '' ? [] : Array.isArray(v) ? (v as string[]) : String(v).split(',');
const lastArgs = () => {
  const calls = getTickets.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
};
const firstTwo = (box: HTMLElement) =>
  Array.from((box as HTMLSelectElement).options).slice(0, 2).map((o) => o.value);

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
  Element.prototype.hasPointerCapture = vi.fn();
  getTickets.mockReset();
  getTickets.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 50 } });
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TicketsList />
    </QueryClientProvider>,
  );
}

describe('Tickets - multi Status, Priority, Category and Source filters', () => {
  it('are four multi controls, Status, Priority, Category, Source', async () => {
    renderIt();
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(4);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it.each([
    [0, 'status'],
    [1, 'priority'],
    [2, 'category'],
    [3, 'source_channel'],
  ])('control %i sends two values of %s to the service, never with the All placeholder', async (index, key) => {
    const user = userEvent.setup();
    renderIt();
    const box = (await screen.findAllByRole('listbox'))[index];
    const two = firstTwo(box);
    expect(two).toHaveLength(2);
    expect(two).not.toContain('all');
    await user.selectOptions(box, two);
    await waitFor(() => expect(asList(lastArgs()[key])).toEqual(two));
  });

  it('the filters AND across each other', async () => {
    const user = userEvent.setup();
    renderIt();
    const boxes = await screen.findAllByRole('listbox');
    const status = firstTwo(boxes[0]);
    const priority = firstTwo(boxes[1]);
    await user.selectOptions(boxes[0], status);
    await user.selectOptions(boxes[1], priority);
    await waitFor(() => {
      expect(asList(lastArgs().status)).toEqual(status);
      expect(asList(lastArgs().priority)).toEqual(priority);
    });
  });
});
