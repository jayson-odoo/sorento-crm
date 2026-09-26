/**
 * specVisibilityService - the service boundary the S1 card was built against
 * (PLAN-spec-visibility-policy). S2 swaps the in-memory mock adapter documented at
 * the top of the service file for a real `apiFetch` call; the Save-body and error
 * tests below assert on the FETCH the S2 implementation must make, not on the mock
 * store the S1 body currently holds - so they stay red until that swap lands
 * (captain's test list, AC-4). The scope-path test (AC-1) exercises the real, already
 * -built pure function and is green from the start.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch }));

import {
  getSpecVisibility,
  saveSpecVisibility,
  specVisibilityScopePath,
} from './specVisibilityService';

function jsonResponse(body: unknown, init: { ok?: boolean; status?: number } = {}): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    async json() {
      return body;
    },
    async text() {
      return JSON.stringify(body);
    },
  } as unknown as Response;
}

const POLICY = {
  specs: null,
  excluded_specs: [{ key: 'thickness', label: 'Thickness' }],
  hidden: [{ key: 'thickness', label: 'Thickness' }],
  source: 'contact',
  source_label: null,
};

function lastCall(): [string, RequestInit | undefined] {
  return apiFetch.mock.calls[apiFetch.mock.calls.length - 1] as [string, RequestInit | undefined];
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe('one path per tier (AC-1)', () => {
  it('maps each scope to its route segment', () => {
    expect(specVisibilityScopePath({ kind: 'contact', contactId: 'c-1' })).toBe(
      '/api/v1/user-management/spec-visibility/contacts/c-1',
    );
    expect(specVisibilityScopePath({ kind: 'segment', segmentCode: 'retail' })).toBe(
      '/api/v1/user-management/spec-visibility/segments/retail',
    );
    expect(specVisibilityScopePath({ kind: 'default' })).toBe(
      '/api/v1/user-management/spec-visibility/default',
    );
  });
});

describe('Save PUTs the drafted rule body (AC-4) - red until S2 calls apiFetch', () => {
  it('sends {spec_keys: ids, excluded_spec_keys: null} under Show only', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ effective: POLICY, override: POLICY }));

    await saveSpecVisibility(
      { kind: 'contact', contactId: 'c-1' },
      { spec_keys: ['material', 'finish'], excluded_spec_keys: null },
    );

    expect(apiFetch).toHaveBeenCalled();
    const [url, init] = lastCall();
    expect(url).toBe('/api/v1/user-management/spec-visibility/contacts/c-1');
    expect(init?.method).toBe('PUT');
    expect(JSON.parse(String(init?.body))).toEqual({
      spec_keys: ['material', 'finish'],
      excluded_spec_keys: null,
    });
  });

  it('sends {spec_keys: null, excluded_spec_keys: ids} under Hide these', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ effective: POLICY, override: POLICY }));

    await saveSpecVisibility(
      { kind: 'segment', segmentCode: 'retail' },
      { spec_keys: null, excluded_spec_keys: ['thickness'] },
    );

    expect(apiFetch).toHaveBeenCalled();
    const [url, init] = lastCall();
    expect(url).toBe('/api/v1/user-management/spec-visibility/segments/retail');
    expect(init?.method).toBe('PUT');
    expect(JSON.parse(String(init?.body))).toEqual({
      spec_keys: null,
      excluded_spec_keys: ['thickness'],
    });
  });

  it('reads the tier with a GET', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ effective: POLICY, override: POLICY }));

    const res = await getSpecVisibility({ kind: 'default' });

    expect(lastCall()[0]).toBe('/api/v1/user-management/spec-visibility/default');
    expect(lastCall()[1]).toBeUndefined();
    expect(res.effective.source).toBe('contact');
  });
});

describe('errors reach the caller via extractApiError - red until S2 wires the real fetch', () => {
  it('throws the FastAPI detail on a rejected save', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({ detail: 'Unknown spec key: ZZT-GHOST' }, { ok: false, status: 422 }),
    );

    await expect(
      saveSpecVisibility(
        { kind: 'contact', contactId: 'c-1' },
        { spec_keys: ['material'], excluded_spec_keys: null },
      ),
    ).rejects.toThrow('Unknown spec key: ZZT-GHOST');
  });

  it('falls back to a readable message when the body carries none', async () => {
    apiFetch.mockResolvedValue(jsonResponse({}, { ok: false, status: 400 }));

    await expect(getSpecVisibility({ kind: 'contact', contactId: 'c-1' })).rejects.toThrow(
      'Failed to load spec visibility',
    );
  });
});
