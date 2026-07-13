import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AuditLogsList from './AuditLogsList';
import type { AuditLog } from '../types/auditLog.types';

// --- next/navigation mock (drives the date-range drill-down seeding) ---------
const replace = vi.fn();
const push = vi.fn();
let searchParams: Record<string, string> = {};
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  usePathname: () => '/system-management/audit-logs',
  useSearchParams: () => ({ get: (k: string) => searchParams[k] ?? null }),
}));

// --- data hook mock ----------------------------------------------------------
const useAuditLogs = vi.fn();
vi.mock('../hooks/useAuditLogs', () => ({
  useAuditLogs: (...a: unknown[]) => useAuditLogs(...a),
}));

// The DataGrid falls back to usePathname() as its column-config listing key and
// keeps the table in a skeleton state until that query resolves. Stub the prefs
// hook to "loaded" so real data rows render synchronously in jsdom.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function mockState(state: Record<string, unknown>) {
  useAuditLogs.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isFetching: false,
    ...state,
  });
}

// jsdom shims the DataGrid primitives touch
beforeEach(() => {
  useAuditLogs.mockReset();
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
});

afterEach(() => cleanup());

/** Grab the params object the component passed to useAuditLogs on its last render. */
function lastQueryArgs(): Record<string, unknown> {
  const calls = useAuditLogs.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
}

describe('AuditLogsList date-range drill-down', () => {
  it('seeds the query from changed_from/changed_to in the URL and shows the active indicator', () => {
    searchParams = {
      changed_from: '2026-07-02T00:00:00.000Z',
      changed_to: '2026-07-02T23:59:59.999Z',
    };
    mockState({});
    renderWithClient(<AuditLogsList />);

    // active-filter indicator renders with the human-readable single-day label
    const indicator = screen.getByTestId('audit-date-filter-active');
    expect(indicator).toBeInTheDocument();
    expect(indicator.textContent).toMatch(/Showing 2026-07-02/);

    // the query was called with the exact ISO bounds from the URL
    const args = lastQueryArgs();
    expect(args.changed_from).toBe('2026-07-02T00:00:00.000Z');
    expect(args.changed_to).toBe('2026-07-02T23:59:59.999Z');
  });

  it('shows a "from → to" label when the range spans multiple days', () => {
    searchParams = {
      changed_from: '2026-07-01T00:00:00.000Z',
      changed_to: '2026-07-03T23:59:59.999Z',
    };
    mockState({});
    renderWithClient(<AuditLogsList />);
    expect(screen.getByTestId('audit-date-filter-active').textContent).toMatch(
      /Showing 2026-07-01 → 2026-07-03/,
    );
  });

  it('does not render the date indicator when no changed_from is present', () => {
    searchParams = {};
    mockState({});
    renderWithClient(<AuditLogsList />);
    expect(screen.queryByTestId('audit-date-filter-active')).not.toBeInTheDocument();
    const args = lastQueryArgs();
    expect(args.changed_from).toBeUndefined();
    expect(args.changed_to).toBeUndefined();
  });

  it('Clear date filter strips the params: drops the indicator, clears the query, and rewrites the URL', () => {
    searchParams = {
      changed_from: '2026-07-02T00:00:00.000Z',
      changed_to: '2026-07-02T23:59:59.999Z',
    };
    mockState({});
    renderWithClient(<AuditLogsList />);

    fireEvent.click(screen.getByRole('button', { name: /clear date filter/i }));

    // URL rewritten to the bare pathname (drops the query string)
    expect(replace).toHaveBeenCalledWith('/system-management/audit-logs');
    // indicator gone and the query no longer carries the bounds
    expect(screen.queryByTestId('audit-date-filter-active')).not.toBeInTheDocument();
    const args = lastQueryArgs();
    expect(args.changed_from).toBeUndefined();
    expect(args.changed_to).toBeUndefined();
  });

  it('renders a resolved contact name in the User column, never the raw contact_id UUID', () => {
    searchParams = {};
    const contactRow: AuditLog = {
      id: 'log-2',
      entity_type: 'complaint',
      entity_id: 'e-9',
      action: 'INSERT',
      user_id: null,
      contact_id: '11111111-2222-3333-4444-555555555555',
      user_display_name: 'Nur Aisyah (Portal)',
      changed_at: '2026-07-02T09:15:00Z',
      old_values: null,
      new_values: { status: 'submitted' },
      description: 'Submitted via portal',
      ip_address: null,
    };
    mockState({
      data: { data: [contactRow], pagination: { total: 1, page: 1, limit: 50 }, empty: false },
    });
    renderWithClient(<AuditLogsList />);

    expect(screen.getByText('Nur Aisyah (Portal)')).toBeInTheDocument();
    // the internal respond_contacts UUID must never surface
    expect(
      screen.queryByText('11111111-2222-3333-4444-555555555555'),
    ).not.toBeInTheDocument();
  });
});
