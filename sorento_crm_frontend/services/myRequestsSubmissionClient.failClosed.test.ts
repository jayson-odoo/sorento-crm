import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch }));

import { myRequestsFetch } from './myRequestsSubmissionClient';

describe('myRequestsFetch fails closed (PAR form parity)', () => {
  beforeEach(() => {
    apiFetch.mockReset();
    apiFetch.mockResolvedValue(new Response('{}', { status: 200 }));
  });

  it('swaps the portal prefix for the my-requests prefix', async () => {
    const init = { method: 'POST' };
    await myRequestsFetch('/api/v1/public/portal/x', init);
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/my-requests/x', init);
  });

  it('passes a my-requests path through', async () => {
    await myRequestsFetch('/api/v1/my-requests/x');
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/my-requests/x', undefined);
  });

  it.each([
    '/api/v1/staff/x',
    'https://evil.example/api/v1/public/portal/x',
    '//host/x',
  ])('refuses %s and never calls apiFetch', async (input) => {
    await expect(Promise.resolve().then(() => myRequestsFetch(input))).rejects.toBeDefined();
    expect(apiFetch).not.toHaveBeenCalled();
  });
});
