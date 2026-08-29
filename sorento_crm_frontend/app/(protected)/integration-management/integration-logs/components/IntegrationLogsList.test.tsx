import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import IntegrationLogsList from './IntegrationLogsList';

// --- next/navigation mock (drills seed filters from the URL) -----------------
const replace = vi.fn();
const push = vi.fn();
let searchParams: Record<string, string | string[]> = {};
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  usePathname: () => '/integration-management/integration-logs',
  useSearchParams: () => ({
    // Mirrors URLSearchParams: `get` returns the first value, `getAll` the list.
    // A fixture may seed either a string or an array (error_contains repeats).
    get: (k: string) => {
      const v = searchParams[k];
      return (Array.isArray(v) ? v[0] : v) ?? null;
    },
    getAll: (k: string) => {
      const v = searchParams[k];
      if (v == null) return [];
      return Array.isArray(v) ? v : [v];
    },
    // `useListStateFromUrl` reads the whole query string (S3-01), so the stand-in
    // has to answer that too, not just `get`/`getAll`.
    toString: () => {
      const out = new URLSearchParams();
      for (const [k, v] of Object.entries(searchParams)) {
        for (const one of Array.isArray(v) ? v : [v]) out.append(k, one);
      }
      return out.toString();
    },
  }),
}));

// --- data + mutation hook mocks ---------------------------------------------
const useIntegrationLogs = vi.fn();
const retryMutate = vi.fn();
vi.mock('../hooks/useIntegrationLogs', () => ({
  useIntegrationLogs: (...a: unknown[]) => useIntegrationLogs(...a),
  useRetryIntegrationLog: () => ({ mutate: retryMutate, isPending: false }),
}));

// DataGrid falls back to usePathname() as its column-config listing key and stays
// in a skeleton state until that query resolves; stub the prefs hook as "loaded".
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function mockData(over: Record<string, unknown> = {}) {
  useIntegrationLogs.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true },
    isLoading: false,
    refetch: vi.fn(),
    isRefetching: false,
    ...over,
  });
}

/** The filter args the component passed to useIntegrationLogs on its last render. */
function lastArgs(): Record<string, unknown> {
  const calls = useIntegrationLogs.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
}

/** Open the custom filter DropdownMenu (the "Filters" trigger). */
function openFilters() {
  // The trigger's accessible name may include the active-count badge ("Filters 2").
  // Radix DropdownMenu opens on pointerdown (mouse), not click.
  const trigger = screen.getByRole('button', { name: /^Filters/i });
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' });
  fireEvent.pointerUp(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' });
}

beforeEach(() => {
  useIntegrationLogs.mockReset();
  retryMutate.mockReset();
  replace.mockReset();
  push.mockReset();
  searchParams = {};
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
  (Element.prototype as unknown as { hasPointerCapture: unknown }).hasPointerCapture = vi.fn();
  (Element.prototype as unknown as { releasePointerCapture: unknown }).releasePointerCapture =
    vi.fn();
});

afterEach(() => cleanup());

describe('IntegrationLogsList - System Health drill-down seeding', () => {
  it('seeds status, integration_channel and created_from from the URL into the query', () => {
    searchParams = {
      status: 'failed',
      integration_channel: 'respond_io',
      created_from: '2026-07-05T09:00:00.000Z',
    };
    mockData();
    renderWithClient(<IntegrationLogsList />);

    const args = lastArgs();
    expect(args.status).toBe('failed');
    expect(args.integration_channel).toBe('respond_io');
    expect(args.created_from).toBe('2026-07-05T09:00:00.000Z');
  });

  it('defaults to no filters (all channels/statuses) when the URL is bare', () => {
    searchParams = {};
    mockData();
    renderWithClient(<IntegrationLogsList />);

    const args = lastArgs();
    // 'all' collapses to undefined before hitting the query
    expect(args.status).toBeUndefined();
    expect(args.integration_channel).toBeUndefined();
    expect(args.created_from).toBeUndefined();
  });

  it('surfaces an off-list (drill-down) channel as its own select option', () => {
    // respond_io is NOT in the component's fixed KNOWN_CHANNELS list.
    searchParams = { integration_channel: 'respond_io' };
    mockData();
    renderWithClient(<IntegrationLogsList />);

    openFilters();
    // the extra option is injected so the Select can display the active channel
    const options = screen.getAllByText('respond_io');
    expect(options.length).toBeGreaterThan(0);
  });

  it('shows the "created_from" active indicator inside the filter panel when seeded', () => {
    searchParams = { created_from: '2026-07-05T09:00:00.000Z' };
    mockData();
    renderWithClient(<IntegrationLogsList />);

    openFilters();
    expect(screen.getByTestId('integration-created-from-active')).toBeInTheDocument();
  });

  it('Clear Filters resets the query filters and rewrites the URL to the bare path', () => {
    searchParams = {
      status: 'failed',
      integration_channel: 'respond_io',
      created_from: '2026-07-05T09:00:00.000Z',
    };
    mockData();
    renderWithClient(<IntegrationLogsList />);

    openFilters();
    fireEvent.click(screen.getByRole('button', { name: /clear filters/i }));

    expect(replace).toHaveBeenCalledWith('/integration-management/integration-logs');
    const args = lastArgs();
    expect(args.status).toBeUndefined();
    expect(args.integration_channel).toBeUndefined();
    expect(args.created_from).toBeUndefined();
  });
});

describe('IntegrationLogsList - failure-cause drill-down (OBS-S1-19, OBS-S1-20)', () => {
  it('seeds status_code and error_contains from the URL into the query', () => {
    searchParams = {
      status: 'failed',
      integration_channel: 'respond_io',
      status_code: '401',
      error_contains: ["Client error '", "/message'"],
    };
    mockData();
    renderWithClient(<IntegrationLogsList />);

    const args = lastArgs();
    expect(args.status_code).toBe('401');
    // AND-ed terms: one alone cannot separate two faults sharing a prefix.
    expect(args.error_contains).toEqual(["Client error '", "/message'"]);
  });

  it('shows a banner naming the cause being filtered', () => {
    // Without this the list is silently narrowed and reads as "only 428 rows
    // exist", with no on-screen reason and no control in the filter panel.
    searchParams = { status_code: '401', error_contains: ["Client error '"] };
    mockData();
    renderWithClient(<IntegrationLogsList />);

    const banner = screen.getByTestId('integration-logs-cause-filter');
    expect(banner).toHaveTextContent('HTTP 401');
    expect(banner).toHaveTextContent("Client error '");
  });

  it('clearing the cause banner widens back to all failures', () => {
    searchParams = { status: 'failed', status_code: '401', error_contains: ["Client error '"] };
    mockData();
    renderWithClient(<IntegrationLogsList />);

    fireEvent.click(screen.getByTestId('integration-logs-cause-filter-clear'));

    const args = lastArgs();
    expect(args.status_code).toBeUndefined();
    expect(args.error_contains).toBeUndefined();
    // the channel/status drill-down survives - only the cause narrowing is dropped
    expect(args.status).toBe('failed');
  });

  it('renders no cause banner when the URL carries no cause filter', () => {
    searchParams = { status: 'failed' };
    mockData();
    renderWithClient(<IntegrationLogsList />);
    expect(screen.queryByTestId('integration-logs-cause-filter')).not.toBeInTheDocument();
  });
});
