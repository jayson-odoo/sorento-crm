/**
 * PROJECT-REGISTER-V2 G3: the project list sends no brand filter param, even if a caller still
 * hands one in (UAC G2: the server ignores it; the client stops sending it).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, apiFetch: (...args: unknown[]) => apiFetch(...args) };
});

import { listProjects } from './projectService';

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue(
    new Response(JSON.stringify({ data: [], pagination: { total: 0, page: 1, limit: 50 } }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }),
  );
});

describe('listProjects', () => {
  it('sends no brand_id param', async () => {
    await listProjects({ brand_id: ['b1'], developer_party_id: ['d1'] } as never);
    const url = String(apiFetch.mock.calls[0][0]);
    expect(url).toContain('developer_party_id=d1');
    expect(url).not.toContain('brand_id');
  });
});
