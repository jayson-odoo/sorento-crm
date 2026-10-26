/**
 * PROJECT-REG-PORTAL rework: approve and reject are calls on the PROJECT, the list takes the
 * approval filters, and the staff pickers ask for approved projects only (RW3, RW5, RW6, RW7, RW8).
 *
 * Names bound here (the plan fixes the routes, not the FE function names): `approveProject`,
 * `rejectProject`, `ProjectListParams.approval_state`, `ProjectListParams.approved_only`.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import {
  approveProject,
  listEditableProjectOptions,
  listProjects,
  rejectProject,
} from './projectService';

const MOUNT = '/api/v1/project-sales/projects';

function ok(body: unknown = {}) {
  return new Response(JSON.stringify(body), { status: 200 });
}

const EXISTING = {
  project_id: 'proj-77',
  project_code: 'PPF2509012',
  title: 'KILANG ALPHA LOT 9001',
};

beforeEach(() => {
  apiFetch.mockReset();
  // A fresh Response per call: a body can be read once, and a test may make two calls.
  apiFetch.mockImplementation(() =>
    Promise.resolve(ok({ data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true })),
  );
});

describe('approve and reject', () => {
  it('approves with POST /projects/{id}/approve and the form body', async () => {
    await approveProject('p-1', { developer_party_id: 'd1', title: 'T' } as never);
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe(`${MOUNT}/p-1/approve`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ developer_party_id: 'd1', title: 'T' });
  });

  it('approves with an empty body when the header button is used', async () => {
    await approveProject('p-1');
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe(`${MOUNT}/p-1/approve`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body ?? '{}')).toEqual({});
  });

  it('rejects with POST /projects/{id}/reject and the reason', async () => {
    await rejectProject('p-1', 'duplicate');
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe(`${MOUNT}/p-1/reject`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ reason: 'duplicate' });
  });

  it('never calls the removed registrations routes', async () => {
    await approveProject('p-1');
    await rejectProject('p-1', 'x');
    for (const call of apiFetch.mock.calls) {
      expect(String(call[0])).not.toContain('/registrations');
    }
  });

  it('throws the server message on a refusal', async () => {
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
    await expect(approveProject('p-1')).rejects.toThrow(
      'PPF2509012 already has this developer and title.',
    );
  });

  it.each([
    ['at the top of the body', { existing_project: EXISTING }],
    ['under details', { details: { existing_project: EXISTING } }],
  ])('a 409 exact duplicate throws an error carrying existingProject (%s)', async (_where, extra) => {
    apiFetch.mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'project_registration_exact_duplicate',
          message: 'PPF2509012 already has this developer and title.',
          detail: null,
          ...extra,
        }),
        { status: 409 },
      ),
    );
    const error = await approveProject('p-1').catch((e: Error) => e);
    expect((error as { existingProject?: unknown }).existingProject).toEqual(EXISTING);
  });

  it('an error without an existing project has none', async () => {
    apiFetch.mockResolvedValue(
      new Response(JSON.stringify({ code: 'project_registration_not_pending', message: 'Decided.' }), {
        status: 409,
      }),
    );
    const error = await approveProject('p-1').catch((e: Error) => e);
    expect((error as { existingProject?: unknown }).existingProject ?? null).toBeNull();
  });
});

describe('the list filters', () => {
  it('sends approval_state and approved_only when asked', async () => {
    await listProjects({ approval_state: 'pending' } as never);
    expect(new URLSearchParams(String(apiFetch.mock.calls[0][0]).split('?')[1]).get('approval_state')).toBe(
      'pending',
    );
    await listProjects({ approved_only: true } as never);
    expect(new URLSearchParams(String(apiFetch.mock.calls[1][0]).split('?')[1]).get('approved_only')).toBe(
      'true',
    );
  });

  it('sends neither by default, so the board and the list still show pending and rejected', async () => {
    await listProjects({});
    const url = String(apiFetch.mock.calls[0][0]);
    expect(url).not.toContain('approval_state');
    expect(url).not.toContain('approved_only');
  });

  it('the Start-menu project picker asks for approved projects only', async () => {
    await listEditableProjectOptions('setia');
    const params = new URLSearchParams(String(apiFetch.mock.calls[0][0]).split('?')[1]);
    expect(params.get('approved_only')).toBe('true');
  });
});
