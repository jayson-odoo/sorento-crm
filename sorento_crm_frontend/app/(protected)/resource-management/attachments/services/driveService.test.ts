/**
 * driveService - request-shaping for the Unified Drive endpoint.
 *
 * Covers UAC: B1 (browse = no recursive), B2/B8 (recursive flag), C6 (pagination),
 * filter passthrough, access_levels repetition.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import {
  getDriveContents,
  isFolderItem,
  isFileItem,
} from './driveService';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

function ok(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as unknown as Response;
}

function url(): string {
  return String(apiFetch.mock.calls[0][0]);
}
function paramsOf(): URLSearchParams {
  return new URLSearchParams(url().split('?')[1] ?? '');
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe('getDriveContents', () => {
  it('B1: browse (empty query, no filter) does NOT send recursive', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1 }, empty: true, recursive: false }));
    await getDriveContents({ pageIndex: 0, pageSize: 50, directory_id: 'dir-1' });
    const p = paramsOf();
    expect(p.get('directory_id')).toBe('dir-1');
    expect(p.get('recursive')).toBeNull();
    expect(p.get('page')).toBe('1');
    expect(p.get('limit')).toBe('50');
  });

  it('B2/B8: recursive=true is forwarded when set', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1 }, empty: true, recursive: true }));
    await getDriveContents({ pageIndex: 0, pageSize: 50, searchQuery: 'invoice', recursive: true });
    const p = paramsOf();
    expect(p.get('recursive')).toBe('true');
    expect(p.get('query')).toBe('invoice');
  });

  it('C6: pagination maps pageIndex -> 1-based page', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 3 }, empty: true, recursive: false }));
    await getDriveContents({ pageIndex: 2, pageSize: 25 });
    const p = paramsOf();
    expect(p.get('page')).toBe('3');
    expect(p.get('limit')).toBe('25');
  });

  it('omits directory_id at root and forwards file filters + sort/dir', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1 }, empty: true, recursive: false }));
    await getDriveContents({
      pageIndex: 0,
      pageSize: 50,
      directory_id: null,
      sorting: [{ id: 'size', desc: true }],
      attachment_type_id: 'type-9',
      uploaded_by: 'user-7',
      link_status: 'linked',
      storage_status: 'missing',
      is_deleted: true,
    });
    const p = paramsOf();
    expect(p.get('directory_id')).toBeNull();
    expect(p.get('sort')).toBe('size');
    expect(p.get('dir')).toBe('desc');
    expect(p.get('attachment_type_id')).toBe('type-9');
    expect(p.get('uploaded_by')).toBe('user-7');
    expect(p.get('link_status')).toBe('linked');
    expect(p.get('storage_status')).toBe('missing');
    expect(p.get('is_deleted')).toBe('true');
  });

  it('repeats access_levels and sends access_levels_match', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1 }, empty: true, recursive: false }));
    await getDriveContents({
      pageIndex: 0,
      pageSize: 50,
      access_levels: ['dealer', 'end_user'],
      access_levels_match: 'all',
    });
    const p = paramsOf();
    expect(p.getAll('access_levels')).toEqual(['dealer', 'end_user']);
    expect(p.get('access_levels_match')).toBe('all');
  });

  it('throws an extracted error on non-ok', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 500,
      headers: { get: () => 'application/json' },
      json: async () => ({ detail: 'boom' }),
      text: async () => '',
    } as unknown as Response);
    await expect(getDriveContents({ pageIndex: 0, pageSize: 50 })).rejects.toThrow('boom');
  });
});

describe('discriminators', () => {
  it('isFolderItem / isFileItem narrow by kind', () => {
    const folder = { kind: 'folder', id: 'f1', name: 'A', parent_id: null, sort_order: 0 } as const;
    const file = { kind: 'file', id: 'a1' } as never;
    expect(isFolderItem(folder)).toBe(true);
    expect(isFileItem(folder)).toBe(false);
    expect(isFileItem(file)).toBe(true);
  });
});
