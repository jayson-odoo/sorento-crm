import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
import { apiFetch } from '@/lib/api';
import { escalateFormTracking } from './formSLAService';

describe('escalateFormTracking (TCK-28)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('POSTs reason and returns the escalation result', async () => {
    (apiFetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ tracking_id: 't1', current_tier: 2, assigned_to_id: 'u1', assigned_to_name: 'Lead', due_at: null, escalation_reason: 'manual: x' }),
    });
    const res = await escalateFormTracking('t1', 'needs lead');
    expect(res.current_tier).toBe(2);
    const [url, init] = (apiFetch as any).mock.calls[0];
    expect(url).toContain('/form-sla-tracking/t1/escalate');
    expect((init as RequestInit).method).toBe('POST');
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ reason: 'needs lead' });
  });

  it('throws the backend detail on 422 (top tier / no assignee)', async () => {
    (apiFetch as any).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Already at the highest tier; cannot escalate further.' }),
    });
    await expect(escalateFormTracking('t1', 'x')).rejects.toThrow(/highest tier/);
  });
});
