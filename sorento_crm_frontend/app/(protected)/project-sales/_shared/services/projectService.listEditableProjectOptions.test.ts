/**
 * Should fix 2 (PR #1219 round 1) - the Start-menu project picker must find every project the
 * user can edit, not only the first page of the newest ones.
 *
 * `can_edit` is filtered client-side, so a company with more editable-but-older projects than
 * fit on one page used to hide them entirely: page 1 (limit 50, `created_at desc`) can be all
 * non-editable rows while the caller's own editable projects sit on page 2+. The fix pages
 * through with the backend's own max page size (`MAX_PAGE_LIMIT`, 1000) until every row is
 * fetched, so a `can_edit: false` row on a later page is still reached.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));
vi.mock('@/lib/api-client', () => ({
  extractApiError: vi.fn(async () => 'Backend said no'),
}));

import { listEditableProjectOptions } from './projectService';

function ok(body: unknown) {
  return { ok: true, json: async () => body };
}

function project(overrides: Record<string, unknown> = {}) {
  return {
    id: 'p-default',
    title: 'Default project',
    project_code: 'PRJ-000000',
    developer_name: 'Dev',
    can_edit: true,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('listEditableProjectOptions', () => {
  it('finds a can_edit project sitting on a later page than the first', async () => {
    // Page 1: 1000 non-editable projects (the newest ones). Page 2: one editable project.
    const page1 = Array.from({ length: 1000 }, (_, i) =>
      project({ id: `p-${i}`, title: `Project ${i}`, can_edit: false }),
    );
    const page2 = [project({ id: 'p-old-editable', title: 'Setia Alam', can_edit: true })];

    apiFetch
      .mockResolvedValueOnce(ok({ data: page1, pagination: { total: 1001, page: 1, limit: 1000 } }))
      .mockResolvedValueOnce(ok({ data: page2, pagination: { total: 1001, page: 2, limit: 1000 } }));

    const options = await listEditableProjectOptions('');

    expect(apiFetch).toHaveBeenCalledTimes(2);
    expect(options).toHaveLength(1);
    expect(options[0]).toMatchObject({ value: 'p-old-editable', label: 'Setia Alam' });
  });

  it('requests the backend max page limit, not the old 50', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 1000 } }));

    await listEditableProjectOptions('');

    const [url] = apiFetch.mock.calls[0];
    expect(url).toContain('limit=1000');
  });

  it('stops after one page when everything has been fetched', async () => {
    apiFetch.mockResolvedValue(
      ok({ data: [project({ id: 'p-1', can_edit: true })], pagination: { total: 1, page: 1, limit: 1000 } }),
    );

    const options = await listEditableProjectOptions('');

    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(options).toHaveLength(1);
  });
});
