import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AuditLogsList from './AuditLogsList';
import type { AuditLog } from '../types/auditLog.types';

// AC-13 (identity S0, reviewer pass at 03d3b474 S2): the record is shown by its
// label (entity_label), never by its raw entity_id, in the list and the drawer.

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const useAuditLogs = vi.fn();

vi.mock('../hooks/useAuditLogs', () => ({
  useAuditLogs: (...a: unknown[]) => useAuditLogs(...a),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => null,
  useSearchParams: () => ({ get: () => null }),
}));

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

const RECORD_ID = '9d8c7b6a-5f4e-4d3c-8b2a-1908f7e6d5c4';

const ROW: AuditLog = {
  id: 'log-record-1',
  entity_type: 'users',
  entity_id: RECORD_ID,
  entity_label: 'User Aisyah',
  action: 'UPDATE',
  user_id: null,
  actor_type: 'system',
  actor_label: 'System',
  changed_at: '2026-06-30T08:30:00Z',
  old_values: { name: 'Old' },
  new_values: { name: 'New' },
  description: null,
  ip_address: null,
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

describe('AuditLogsList record column and drawer (AC-13, no UUID)', () => {
  it('shows the record label in the list, never the entity_id', () => {
    mockState({ data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 }, empty: false } });
    renderWithClient(<AuditLogsList />);
    expect(screen.getByText('User Aisyah')).toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain(RECORD_ID);
  });

  it('shows the record label in the detail drawer, never the entity_id', () => {
    mockState({ data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 }, empty: false } });
    renderWithClient(<AuditLogsList />);
    fireEvent.click(screen.getByText('User Aisyah'));
    expect(screen.getAllByText('Record').some((el) => el.tagName === 'DT')).toBe(true);
    expect(screen.getAllByText('User Aisyah').length).toBeGreaterThanOrEqual(2);
    expect(document.body.innerHTML).not.toContain(RECORD_ID);
  });
});
