import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

import AuditTrail from './AuditTrail';
import type { AuditLogEntry } from '@/types/audit.types';

// AC-13 (FE half, identity S0): AuditTrail renders "by <actor_label>", falling back
// to user_display_name, then "System" - never a raw user_id.

const useAuditLogs = vi.fn();

vi.mock('@/hooks/useAuditLogs', () => ({
  useAuditLogs: (...a: unknown[]) => useAuditLogs(...a),
}));

afterEach(() => cleanup());

function entry(overrides: Partial<AuditLogEntry>): AuditLogEntry {
  return {
    id: `log-${Math.random()}`,
    entity_type: 'users',
    entity_id: 'entity-1',
    action: 'UPDATE',
    user_id: 'a1b2c3d4-e5f6-47a8-9012-3456789abcde',
    changed_at: '2026-09-26T08:00:00Z',
    old_values: { name: 'Old' },
    new_values: { name: 'New' },
    description: null,
    ip_address: '10.0.0.1',
    ...overrides,
  };
}

function mockEntries(entries: AuditLogEntry[]) {
  useAuditLogs.mockReturnValue({
    data: { data: entries, pagination: { total: entries.length, page: 1, limit: 50 }, empty: entries.length === 0 },
    isLoading: false,
  });
}

describe('AuditTrail actor rendering (AC-13)', () => {
  it('shows "by <actor_label>" for an impersonation row', () => {
    mockEntries([entry({ actor_label: 'Nurain on behalf of Aisyah', auth_method: 'impersonation' })]);
    render(<AuditTrail entityType="users" entityId="entity-1" />);
    expect(screen.getByText(/by Nurain on behalf of Aisyah/)).toBeInTheDocument();
  });

  it('shows "by <actor_label>" for a portal-contact-with-no-user row', () => {
    mockEntries([entry({ actor_label: 'Portal: Aisyah (no user)', actor_type: 'contact' })]);
    render(<AuditTrail entityType="users" entityId="entity-1" />);
    expect(screen.getByText(/by Portal: Aisyah \(no user\)/)).toBeInTheDocument();
  });

  it('shows "by <actor_label>" for a worker/background-job row', () => {
    mockEntries([entry({ actor_label: 'Background job for Aisyah', actor_type: 'worker' })]);
    render(<AuditTrail entityType="users" entityId="entity-1" />);
    expect(screen.getByText(/by Background job for Aisyah/)).toBeInTheDocument();
  });

  it('falls back to "by System" and never renders the raw user_id when there is no label and no display name', () => {
    const userId = 'a1b2c3d4-e5f6-47a8-9012-3456789abcde';
    mockEntries([entry({ user_id: userId, actor_label: null, user_display_name: null })]);
    render(<AuditTrail entityType="users" entityId="entity-1" />);
    expect(screen.getByText(/by System/)).toBeInTheDocument();
    expect(screen.queryByText(userId)).not.toBeInTheDocument();
    expect(document.body.textContent || '').not.toContain(userId);
  });
});
