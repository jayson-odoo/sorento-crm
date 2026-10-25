/**
 * projectRegistrationService calls the routes the backend mounts. The project-sales router is
 * mounted under `/api/v1/project-sales` and its projects router under `/projects`
 * (app/api/v1/__init__.py, app/api/v1/projects/__init__.py), so the registrations queue is
 * `/api/v1/project-sales/projects/registrations`, next to the staff `/projects/` routes.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

import {
  approveProjectRegistration,
  getProjectRegistration,
  getProjectRegistrations,
  rejectProjectRegistration,
} from './projectRegistrationService';

const MOUNT = '/api/v1/project-sales/projects/registrations';

function ok(body: unknown = {}) {
  return new Response(JSON.stringify(body), { status: 200 });
}

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue(
    ok({ data: [], pagination: { total: 0, page: 1, limit: 25 } }),
  );
});

describe('projectRegistrationService', () => {
  it('lists from the mounted path with the DataGrid params and the status', async () => {
    await getProjectRegistrations({
      pageIndex: 1,
      pageSize: 25,
      sorting: [{ id: 'submitted_at', desc: true }],
      searchQuery: 'setia',
      status: 'all',
    });

    const url = String(apiFetch.mock.calls[0][0]);
    expect(url.startsWith(`${MOUNT}/?`) || url.startsWith(`${MOUNT}?`)).toBe(
      true,
    );
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('page')).toBe('2');
    expect(params.get('limit')).toBe('25');
    expect(params.get('sort')).toBe('submitted_at');
    expect(params.get('dir')).toBe('desc');
    expect(params.get('query')).toBe('setia');
    expect(params.get('status')).toBe('all');
  });

  it('reads one registration from /{id}', async () => {
    await getProjectRegistration('reg-1');
    expect(apiFetch.mock.calls[0][0]).toBe(`${MOUNT}/reg-1`);
  });

  it('approves with POST /{id}/approve and the form body', async () => {
    await approveProjectRegistration('reg-1', {
      title: 'T',
      developer_party_id: 'd1',
    } as never);
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe(`${MOUNT}/reg-1/approve`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      title: 'T',
      developer_party_id: 'd1',
    });
  });

  it('rejects with POST /{id}/reject and the reason', async () => {
    await rejectProjectRegistration('reg-1', 'duplicate');
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe(`${MOUNT}/reg-1/reject`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ reason: 'duplicate' });
  });

  it('throws the server message on a refusal (the 409 text reaches the form)', async () => {
    apiFetch.mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'project_registration_exact_duplicate',
          message: 'PPF2509012 already has this developer and title.',
          detail: null,
        }),
        { status: 409 },
      ),
    );
    await expect(
      approveProjectRegistration('reg-1', { title: 'T' } as never),
    ).rejects.toThrow('PPF2509012 already has this developer and title.');
  });
});
