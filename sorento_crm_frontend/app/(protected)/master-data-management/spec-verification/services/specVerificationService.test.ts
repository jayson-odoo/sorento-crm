/**
 * specVerificationService - worklist query assembly, write bodies, and the 409
 * taxonomy on the single verify (AC-D.4: `values_changed` vs `exceptions_open` are
 * distinguishable). Traces to the API contract block at the top of the service file
 * and AC-D.11/D.16/D.23/D.24.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import {
  getSpecVerificationWorklist,
  SpecVerifyConflictError,
  unverifySpec,
  unverifySpecBulk,
  verifySpec,
  verifySpecBulk,
} from './specVerificationService';

const mockedFetch = vi.mocked(apiFetch);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => vi.clearAllMocks());

describe('getSpecVerificationWorklist - query-string assembly', () => {
  const WORKLIST_RESPONSE = {
    data: [],
    pagination: { total: 0, page: 1, limit: 25 },
    summary: { total: 0, verified: 0, needs_reverify: 0, unverified: 0 },
    classes: [],
  };

  it('omits state, class_label and include_discontinued when unset', async () => {
    mockedFetch.mockResolvedValue(jsonResponse(WORKLIST_RESPONSE));

    await getSpecVerificationWorklist({
      pageIndex: 0,
      pageSize: 25,
      sorting: [],
      searchQuery: '',
      state: '',
      class_label: '',
      include_discontinued: false,
    });

    const [url] = mockedFetch.mock.calls[0];
    expect(url).toContain(
      '/api/v1/master-data/product-specifications/verification/worklist?',
    );
    const qs = new URLSearchParams(String(url).split('?')[1]);
    expect(qs.has('state')).toBe(false);
    expect(qs.has('class_label')).toBe(false);
    expect(qs.has('include_discontinued')).toBe(false);
    expect(qs.get('page')).toBe('1');
    expect(qs.get('limit')).toBe('25');
  });

  it('carries state, class_label and include_discontinued=true when set', async () => {
    mockedFetch.mockResolvedValue(jsonResponse(WORKLIST_RESPONSE));

    await getSpecVerificationWorklist({
      pageIndex: 2,
      pageSize: 50,
      sorting: [{ id: 'coverage', desc: true }],
      searchQuery: 'WC100',
      state: 'needs_reverify',
      class_label: 'Kitchen Sink',
      include_discontinued: true,
    });

    const [url] = mockedFetch.mock.calls[0];
    const qs = new URLSearchParams(String(url).split('?')[1]);
    expect(qs.get('state')).toBe('needs_reverify');
    expect(qs.get('class_label')).toBe('Kitchen Sink');
    expect(qs.get('include_discontinued')).toBe('true');
    expect(qs.get('page')).toBe('3');
    expect(qs.get('limit')).toBe('50');
    expect(qs.get('sort')).toBe('coverage');
    expect(qs.get('dir')).toBe('desc');
    expect(qs.get('query')).toBe('WC100');
  });

  it('does not send include_discontinued at all when explicitly false', async () => {
    mockedFetch.mockResolvedValue(jsonResponse(WORKLIST_RESPONSE));

    await getSpecVerificationWorklist({
      pageIndex: 0,
      pageSize: 25,
      sorting: [],
      searchQuery: '',
      state: 'verified',
      class_label: '',
      include_discontinued: false,
    });

    const [url] = mockedFetch.mock.calls[0];
    const qs = new URLSearchParams(String(url).split('?')[1]);
    expect(qs.get('state')).toBe('verified');
    expect(qs.has('include_discontinued')).toBe(false);
  });

  it('throws a readable error on a non-ok response', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({ detail: 'nope' }, 500));

    await expect(
      getSpecVerificationWorklist({
        pageIndex: 0,
        pageSize: 25,
        sorting: [],
        searchQuery: '',
      }),
    ).rejects.toThrow('nope');
  });

  it('falls back to the generic message when a non-ok response carries no detail', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({}, 500));

    await expect(
      getSpecVerificationWorklist({
        pageIndex: 0,
        pageSize: 25,
        sorting: [],
        searchQuery: '',
      }),
    ).rejects.toThrow('Server error. Try again or contact support.');
  });
});

describe('write bodies', () => {
  it('verifySpecBulk posts { items }', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({ results: [], counts: { verified: 0, skipped: 0 } }),
    );

    await verifySpecBulk([{ product_code: 'WC100', values_hash: 'h1' }]);

    const [url, init] = mockedFetch.mock.calls[0];
    expect(url).toBe(
      '/api/v1/master-data/product-specifications/verification/verify-bulk',
    );
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      items: [{ product_code: 'WC100', values_hash: 'h1' }],
    });
  });

  it('unverifySpecBulk posts { product_codes }', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({ results: [], counts: { unverified: 0, no_change: 0 } }),
    );

    await unverifySpecBulk(['WC100', 'WC200']);

    const [url, init] = mockedFetch.mock.calls[0];
    expect(url).toBe(
      '/api/v1/master-data/product-specifications/verification/unverify-bulk',
    );
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      product_codes: ['WC100', 'WC200'],
    });
  });

  it('verifySpec posts { product_code, values_hash } to the single route', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({
        product_code: 'WC100',
        outcome: 'verified',
        verification: { state: 'verified' },
        values_hash: 'h1',
      }),
    );

    await verifySpec({ product_code: 'WC100', values_hash: 'h1' });

    const [url, init] = mockedFetch.mock.calls[0];
    expect(url).toBe(
      '/api/v1/master-data/product-specifications/verification/verify',
    );
    expect(JSON.parse(String(init?.body))).toEqual({
      product_code: 'WC100',
      values_hash: 'h1',
    });
  });

  it('unverifySpec posts { product_code } to the single route', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({
        product_code: 'WC100',
        outcome: 'unverified',
        verification: {},
      }),
    );

    await unverifySpec({ product_code: 'WC100' });

    const [url, init] = mockedFetch.mock.calls[0];
    expect(url).toBe(
      '/api/v1/master-data/product-specifications/verification/unverify',
    );
    expect(JSON.parse(String(init?.body))).toEqual({ product_code: 'WC100' });
  });
});

describe('SpecVerifyConflictError - both 409 serialisations', () => {
  it('parses a top-level { error, ... } body', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse(
        {
          error: 'values_changed',
          values_hash: 'h2',
          verification: { state: 'unverified' },
        },
        409,
      ),
    );

    const thrown = (await verifySpec({
      product_code: 'WC100',
      values_hash: 'h1',
    }).catch((e) => e)) as Error;

    expect(thrown).toBeInstanceOf(SpecVerifyConflictError);
    const conflict = thrown as SpecVerifyConflictError;
    expect(conflict.reason).toBe('values_changed');
    expect(conflict.valuesHash).toBe('h2');
    expect(conflict.verification).toEqual({ state: 'unverified' });
  });

  it('parses the body nested under the AppException { detail } envelope', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse(
        {
          detail: {
            error: 'exceptions_open',
            exceptions: [{ spec_key: 'shape', reason: 'shape_mismatch' }],
          },
        },
        409,
      ),
    );

    const thrown = (await verifySpec({
      product_code: 'WC100',
      values_hash: 'h1',
    }).catch((e) => e)) as Error;

    expect(thrown).toBeInstanceOf(SpecVerifyConflictError);
    const conflict = thrown as SpecVerifyConflictError;
    expect(conflict.reason).toBe('exceptions_open');
    expect(conflict.exceptions).toEqual([
      { spec_key: 'shape', reason: 'shape_mismatch' },
    ]);
  });

  it("carries the server's own message when it sent one, not the local fallback", async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse(
        {
          error: 'exceptions_open',
          message:
            'Answer the open specification questions before confirming this product.',
          exceptions: [{ spec_key: 'shape' }],
        },
        409,
      ),
    );

    const thrown = (await verifySpec({
      product_code: 'WC100',
      values_hash: 'h1',
    }).catch((e) => e)) as Error;

    expect(thrown.message).toBe(
      'Answer the open specification questions before confirming this product.',
    );
  });

  it('falls back to the local message when the 409 body carries none', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({ error: 'values_changed' }, 409),
    );

    const thrown = (await verifySpec({
      product_code: 'WC100',
      values_hash: 'h1',
    }).catch((e) => e)) as Error;

    expect(thrown.message).toBe('Could not verify this product');
  });

  it('a non-409 error falls through to extractApiError, never SpecVerifyConflictError', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({ detail: 'Not permitted' }, 403),
    );

    const thrown = (await verifySpec({
      product_code: 'WC100',
      values_hash: 'h1',
    }).catch((e) => e)) as Error;

    expect(thrown).not.toBeInstanceOf(SpecVerifyConflictError);
    expect(thrown.message).toBe('Not permitted');
  });

  it('a 409 whose body carries neither known error code falls through as a plain error', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({ error: 'something_else' }, 409),
    );

    const thrown = (await verifySpec({
      product_code: 'WC100',
      values_hash: 'h1',
    }).catch((e) => e)) as Error;

    expect(thrown).not.toBeInstanceOf(SpecVerifyConflictError);
  });
});

describe('the class facet', () => {
  it('is read off the worklist response, not the spec registry', async () => {
    // The registry's `class` key is open vocabulary and its allowed_values are empty
    // on purpose, so the labels can only come from the rows the worklist counted.
    mockedFetch.mockResolvedValue(
      jsonResponse({
        data: [],
        pagination: { total: 0, page: 1, limit: 25 },
        summary: { total: 0, verified: 0, needs_reverify: 0, unverified: 0 },
        classes: ['Bidet Spray', 'Kitchen Sink'],
      }),
    );

    const response = await getSpecVerificationWorklist({
      pageIndex: 0,
      pageSize: 25,
      sorting: [],
      searchQuery: '',
    });

    expect(response.classes).toEqual(['Bidet Spray', 'Kitchen Sink']);
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });
});
