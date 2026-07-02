import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AuditLogsList from './AuditLogsList';
import type { AuditLog } from '../types/auditLog.types';

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const useAuditLogs = vi.fn();

vi.mock('../hooks/useAuditLogs', () => ({
  useAuditLogs: (...a: unknown[]) => useAuditLogs(...a),
}));

// jsdom does not implement these browser APIs the DataGrid primitives touch.
beforeEach(() => {
  useAuditLogs.mockReset();
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

const ROW: AuditLog = {
  id: 'log-1',
  entity_type: 'complaint',
  entity_id: 'entity-abc-123',
  action: 'UPDATE',
  user_id: 'u-1',
  user_display_name: 'Jane Admin',
  changed_at: '2026-06-30T08:30:00Z',
  old_values: { status: 'open' },
  new_values: { status: 'closed' },
  description: 'Status changed to closed',
  ip_address: '10.0.0.5',
};

function mockState(state: Record<string, unknown>) {
  useAuditLogs.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isFetching: false,
    ...state,
  });
}

describe('AuditLogsList', () => {
  it('renders the search affordance while loading', () => {
    mockState({ isLoading: true });
    renderWithClient(<AuditLogsList />);
    expect(screen.getByPlaceholderText(/search by entity id/i)).toBeInTheDocument();
  });

  it('renders an empty state when there are no audit entries', () => {
    mockState({
      data: { data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true },
    });
    renderWithClient(<AuditLogsList />);
    expect(screen.getByText(/no audit log entries found/i)).toBeInTheDocument();
  });

  it('renders audit rows with human-readable user and action, no raw user_id label', () => {
    mockState({
      data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 }, empty: false },
    });
    renderWithClient(<AuditLogsList />);
    expect(screen.getByText('Jane Admin')).toBeInTheDocument();
    expect(screen.getByText('UPDATE')).toBeInTheDocument();
    expect(screen.getByText('Status changed to closed')).toBeInTheDocument();
    // user_id UUID must not surface as a label
    expect(screen.queryByText('u-1')).not.toBeInTheDocument();
  });

  it('renders an error state with a retry affordance', () => {
    mockState({ isError: true, error: new Error('Failed to load audit logs') });
    renderWithClient(<AuditLogsList />);
    expect(screen.getByText('Failed to load audit logs.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});
