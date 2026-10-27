/**
 * BULK-CONTACT-ACCESS U19a: staff requests run under ONE active company, so the access-sheet
 * request always asks for the caller's grants (`company_scope=grants`), preview and apply alike.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const api = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', () => api);

import { previewAccessSheet, applyAccessSheet } from './contactAccessSheetService';

const ok = { ok: true, json: async () => ({ dry_run: true, counts: {}, errors: [], blocks: [] }) };
const file = new File(['x'], 'sheet.csv', { type: 'text/csv' });

beforeEach(() => {
  api.apiFetch.mockReset();
  api.apiFetch.mockResolvedValue(ok);
});

describe('contactAccessSheetService', () => {
  it('preview posts to the access-sheet endpoint with company_scope=grants', async () => {
    await previewAccessSheet(file);
    const [url, init] = api.apiFetch.mock.calls[0];
    expect(String(url)).toContain('/api/v1/user-management/contacts/access-sheet');
    expect(String(url)).toContain('company_scope=grants');
    expect(init.method).toBe('POST');
    expect((init.body as FormData).get('dry_run')).toBe('true');
  });

  it('apply carries company_scope=grants, dry_run false and the confirmed JSON', async () => {
    await applyAccessSheet(file, { 'alpha bath': ['a1'] });
    const [url, init] = api.apiFetch.mock.calls[0];
    expect(String(url)).toContain('company_scope=grants');
    const body = init.body as FormData;
    expect(body.get('dry_run')).toBe('false');
    expect(JSON.parse(String(body.get('confirmed')))).toEqual({ 'alpha bath': ['a1'] });
  });
});
