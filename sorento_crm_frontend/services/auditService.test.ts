import { describe, it, expect, vi } from 'vitest';

// AUDIT-TRAIL-DIFF AC-6: the record trail asks for its child rows (a complaint's product
// lines). The backend returns them only on this opt-in, so dropping it hides them silently.

const apiFetch = vi.fn();

vi.mock('@/lib/api', () => ({
  apiFetch: (...a: unknown[]) => apiFetch(...a),
}));

import { getAuditLogs } from './auditService';

describe('getAuditLogs', () => {
  it('asks for the record and its child rows', async () => {
    apiFetch.mockResolvedValue(
      new Response(JSON.stringify({ data: [], pagination: { total: 0, page: 1, limit: 200 }, empty: true })),
    );
    await getAuditLogs({ entity_type: 'complaint', entity_id: 'rec-1', limit: 200 });
    const url = new URL(String(apiFetch.mock.calls[0][0]), 'http://x');
    expect(url.pathname).toBe('/api/v1/audit/logs');
    expect(url.searchParams.get('entity_type')).toBe('complaint');
    expect(url.searchParams.get('entity_id')).toBe('rec-1');
    expect(url.searchParams.get('limit')).toBe('200');
    expect(url.searchParams.get('include_children')).toBe('true');
  });
});
