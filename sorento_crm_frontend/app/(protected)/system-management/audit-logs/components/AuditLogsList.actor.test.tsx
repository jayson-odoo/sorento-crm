import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AuditLogsList from './AuditLogsList';
import type { AuditLog } from '../types/auditLog.types';

// AC-13 (FE half, identity S0): the Actor column shows actor_label; the detail
// drawer adds "Actor kind" and "Sign-in method" rows in words; no raw UUID
// (user_id / real_user_id / integration_id) ever appears in the document.

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

const INTEGRATION_ROW: AuditLog = {
  id: 'log-int-1',
  entity_type: 'users',
  entity_id: 'entity-int-1',
  action: 'UPDATE',
  user_id: 'a1b2c3d4-e5f6-47a8-9012-3456789abcde',
  integration_id: 'f1e2d3c4-b5a6-4798-8012-3456789abcde',
  actor_type: 'integration',
  auth_method: 'api_key',
  actor_label: 'Integration: n8n as Ops Bot',
  changed_at: '2026-06-30T08:30:00Z',
  old_values: { status: 'open' },
  new_values: { status: 'closed' },
  description: null,
  ip_address: '10.0.0.5',
};

const SCHEDULER_ROW: AuditLog = {
  id: 'log-sched-1',
  entity_type: 'users',
  entity_id: 'entity-sched-1',
  action: 'UPDATE',
  user_id: null,
  actor_type: 'scheduler',
  job_id: 'daily-reorder-run',
  actor_label: 'Scheduled: daily-reorder-run',
  changed_at: '2026-06-30T08:30:00Z',
  old_values: null,
  new_values: null,
  description: null,
  ip_address: null,
};

const CONTACT_ROW: AuditLog = {
  id: 'log-contact-1',
  entity_type: 'users',
  entity_id: 'entity-contact-1',
  action: 'UPDATE',
  user_id: null,
  contact_id: 'c1c2c3c4-d5d6-4798-8012-3456789abcde',
  actor_type: 'contact',
  auth_method: 'portal_token',
  actor_label: 'Portal: Aisyah (no user)',
  changed_at: '2026-06-30T08:30:00Z',
  old_values: null,
  new_values: null,
  description: null,
  ip_address: '10.0.0.9',
};

const STAFF_PHONE_ROW: AuditLog = {
  id: 'log-staff-1',
  entity_type: 'users',
  entity_id: 'entity-staff-1',
  action: 'UPDATE',
  user_id: 'aaaa1111-e5f6-47a8-9012-3456789abcde',
  actor_type: 'user',
  auth_method: 'phone_otp',
  actor_label: 'Aisyah (phone)',
  changed_at: '2026-06-30T08:30:00Z',
  old_values: { name: 'Old' },
  new_values: { name: 'New' },
  description: null,
  ip_address: '10.0.0.2',
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

describe('AuditLogsList actor column and detail drawer (AC-13)', () => {
  it('renders actor_label in the Actor column, not the raw user_id', () => {
    mockState({
      data: { data: [INTEGRATION_ROW], pagination: { total: 1, page: 1, limit: 50 }, empty: false },
    });
    renderWithClient(<AuditLogsList />);
    expect(screen.getByText('Integration: n8n as Ops Bot')).toBeInTheDocument();
    expect(screen.queryByText(INTEGRATION_ROW.user_id as string)).not.toBeInTheDocument();
    expect(screen.queryByText(INTEGRATION_ROW.integration_id as string)).not.toBeInTheDocument();
  });

  it('opening an integration row shows "Integration" as Actor kind and "API key" as Sign-in method', () => {
    mockState({
      data: { data: [INTEGRATION_ROW], pagination: { total: 1, page: 1, limit: 50 }, empty: false },
    });
    renderWithClient(<AuditLogsList />);
    fireEvent.click(screen.getByText('Integration: n8n as Ops Bot'));
    expect(screen.getByText('Actor kind')).toBeInTheDocument();
    expect(screen.getByText('Integration')).toBeInTheDocument();
    expect(screen.getByText('Sign-in method')).toBeInTheDocument();
    expect(screen.getByText('API key')).toBeInTheDocument();
  });

  it('opening a scheduler row shows "Scheduled" as Actor kind', () => {
    mockState({
      data: { data: [SCHEDULER_ROW], pagination: { total: 1, page: 1, limit: 50 }, empty: false },
    });
    renderWithClient(<AuditLogsList />);
    fireEvent.click(screen.getByText('Scheduled: daily-reorder-run'));
    expect(screen.getByText('Actor kind')).toBeInTheDocument();
    expect(screen.getByText('Scheduled')).toBeInTheDocument();
  });

  it('opening a contact-with-no-user row shows "Portal contact" as Actor kind and "Portal token" as Sign-in method', () => {
    mockState({
      data: { data: [CONTACT_ROW], pagination: { total: 1, page: 1, limit: 50 }, empty: false },
    });
    renderWithClient(<AuditLogsList />);
    fireEvent.click(screen.getByText('Portal: Aisyah (no user)'));
    expect(screen.getByText('Portal contact')).toBeInTheDocument();
    expect(screen.getByText('Portal token')).toBeInTheDocument();
  });

  it('opening a staff phone-sign-in row shows "Staff" as Actor kind and "Phone code" as Sign-in method', () => {
    mockState({
      data: { data: [STAFF_PHONE_ROW], pagination: { total: 1, page: 1, limit: 50 }, empty: false },
    });
    renderWithClient(<AuditLogsList />);
    fireEvent.click(screen.getByText('Aisyah (phone)'));
    expect(screen.getByText('Staff')).toBeInTheDocument();
    expect(screen.getByText('Phone code')).toBeInTheDocument();
  });

  it('never renders a raw UUID (user_id / integration_id / contact_id) anywhere in the document', () => {
    mockState({
      data: {
        data: [INTEGRATION_ROW, SCHEDULER_ROW, CONTACT_ROW, STAFF_PHONE_ROW],
        pagination: { total: 4, page: 1, limit: 50 },
        empty: false,
      },
    });
    renderWithClient(<AuditLogsList />);
    const body = document.body.textContent || '';
    expect(body).not.toContain(INTEGRATION_ROW.user_id);
    expect(body).not.toContain(INTEGRATION_ROW.integration_id);
    expect(body).not.toContain(CONTACT_ROW.contact_id);
    expect(body).not.toContain(STAFF_PHONE_ROW.user_id);
  });
});
