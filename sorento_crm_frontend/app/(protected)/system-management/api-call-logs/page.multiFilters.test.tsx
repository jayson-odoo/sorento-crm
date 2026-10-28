/**
 * FILTER-MULTISELECT PR2: the API call log's Source and Outcome filters take several values (OR within
 * a filter, AND across). They reach the list service as a list or a comma-joined string; either reads
 * the same here. The "All" placeholders are never values.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getApiCallLogs = vi.fn();
vi.mock('./services/apiCallLogService', () => ({
  getApiCallLogs: (...a: unknown[]) => getApiCallLogs(...a),
  getApiCallLogSources: vi.fn(async () => ['mcp', 'n8n', 'unknown']),
}));
vi.mock('./components/ApiCallDetailDrawer', () => ({ ApiCallDetailDrawer: () => null }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/system-management/api-call-logs',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/common/PageHeader', () => ({ PageHeader: ({ title }: { title: string }) => <h1>{title}</h1> }));
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

import ApiCallLogsPage from './page';

const asList = (v: unknown): string[] =>
  v == null || v === '' ? [] : Array.isArray(v) ? (v as string[]) : String(v).split(',');
const lastFilters = () => {
  const calls = getApiCallLogs.mock.calls;
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
  getApiCallLogs.mockReset();
  getApiCallLogs.mockResolvedValue({ data: [], total: 0, page: 1, limit: 50 });
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ApiCallLogsPage />
    </QueryClientProvider>,
  );
}

describe('API call log - multi Source and Outcome filters', () => {
  it('are two multi controls, Source then Outcome', async () => {
    renderIt();
    await screen.findByText('API Call Log');
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(2);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two sources reach the list service, never with the All placeholder', async () => {
    const user = userEvent.setup();
    renderIt();
    const [source] = await screen.findAllByRole('listbox');
    await waitFor(() => expect((source as HTMLSelectElement).options.length).toBe(3));
    await user.selectOptions(source, ['mcp', 'n8n']);
    await waitFor(() => expect(asList(lastFilters().source)).toEqual(['mcp', 'n8n']));
  });

  it('two outcomes reach the list service', async () => {
    const user = userEvent.setup();
    renderIt();
    const boxes = await screen.findAllByRole('listbox');
    await user.selectOptions(boxes[1], ['client_error', 'server_error']);
    await waitFor(() => expect(asList(lastFilters().outcome)).toEqual(['client_error', 'server_error']));
  });

  it('the filters AND across each other', async () => {
    const user = userEvent.setup();
    renderIt();
    const boxes = await screen.findAllByRole('listbox');
    await waitFor(() => expect((boxes[0] as HTMLSelectElement).options.length).toBe(3));
    await user.selectOptions(boxes[0], ['mcp', 'n8n']);
    await user.selectOptions(boxes[1], ['success']);
    await waitFor(() => {
      expect(asList(lastFilters().source)).toEqual(['mcp', 'n8n']);
      expect(asList(lastFilters().outcome)).toEqual(['success']);
    });
  });
});
