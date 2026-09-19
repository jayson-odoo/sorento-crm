/**
 * AutoCount pull + review - service, SR2 red tests.
 *
 * SR2 wires this service to the real backend (`POST/GET /api/v1/autocount/pulls/...`) and
 * deletes the Phase 1 mock (`USE_MOCK`, `hasAutocountPullPermissionMock`, `mockImportJobShim`,
 * the whole `__mocks__/` folder). Every test here mocks `@/lib/api` (`apiFetch`) - the layer
 * `lib/api-client` sits on top of - per repo convention (see `outstandingImportService.test.ts`,
 * `useDemandSeries.test.tsx`).
 *
 * Contract pinned from `documentation/plans/autocount/PLAN-autocount-pull-review.md` ("Routes")
 * and the captain's SR2 brief: every pull route answers
 * `{job_id, phase, progress, header, counts, confirm_blocked_reason, compare, apply_job_id,
 * warnings}`, `header` null or the FoundryX ready header in camelCase
 * (snapshotId, entity, companyCode, extractedAt, expiresAt, recordCount, complete, contentHash,
 * zeroListPriceCount, negativeListPriceCount, ...). Errors are JSON with a top-level `code` and
 * `message` (AC-PL-6) - `codedError` (already imported by this service for start/confirm) reads
 * exactly that shape.
 *
 * RED reason today: `USE_MOCK = true` short-circuits every one of these functions before
 * `apiFetch` is ever called, so every assertion here that `apiFetch` was hit, or was hit with
 * the right method/url/body, fails - not because of a typo in the test, but because the mock
 * branch runs instead of the real one. S6 fails because the mock and its fixtures still exist.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  startPull,
  getCurrentPull,
  getPull,
  getPullRows,
  confirmPull,
  comparePull,
  downloadPullXlsx,
  startPullErrorMessage,
} from './autocountPullService';

function ok(body: unknown, status = 200) {
  return {
    ok: true,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
    clone() {
      return ok(body, status);
    },
  } as unknown as Response;
}

function fail(status: number, body: unknown) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
    clone() {
      return fail(status, body);
    },
  } as unknown as Response;
}

function calledUrl(callIndex = -1): URL {
  const calls = apiFetch.mock.calls;
  if (calls.length === 0) {
    throw new Error('apiFetch was never called - the service is still on its Phase 1 mock branch (USE_MOCK).');
  }
  const call = callIndex === -1 ? calls[calls.length - 1] : calls[callIndex];
  return new URL(String(call[0]), 'http://x');
}

function lastInit(): RequestInit {
  const calls = apiFetch.mock.calls;
  if (calls.length === 0) {
    throw new Error('apiFetch was never called - the service is still on its Phase 1 mock branch (USE_MOCK).');
  }
  return (calls[calls.length - 1][1] ?? {}) as RequestInit;
}

const PRODUCTS_HEADER = {
  snapshotId: '8f1e1c2a-8b7a-4b3e-9b0a-1c2d3e4f5a6b',
  entity: 'products',
  companyCode: 'SRT',
  extractedAt: '2026-09-20T02:00:00Z',
  expiresAt: '2026-09-21T02:00:00Z',
  recordCount: 10,
  complete: true,
  contentHash: 'deadbeef',
  zeroListPriceCount: 0,
  negativeListPriceCount: 0,
};

const REVIEW_PULL = {
  job_id: '3b6a1f2e-9c4d-4a3b-8e2f-1a2b3c4d5e6f',
  entity: 'products',
  phase: 'review',
  progress: null,
  header: PRODUCTS_HEADER,
  counts: {
    received: 10,
    new: 10,
    changed: 0,
    unchanged: 0,
    failed: 0,
    left_out: 0,
    price_to_zero: 0,
  },
  confirm_blocked_reason: null,
  compare: null,
  apply_job_id: null,
  warnings: [],
};

beforeEach(() => {
  apiFetch.mockReset();
});

describe('startPull (AC-PL-3)', () => {
  it('S1: POSTs {entity} to /api/v1/autocount/pulls and returns the mapped pull', async () => {
    apiFetch.mockResolvedValue(ok(REVIEW_PULL));

    const result = await startPull('products');

    expect(calledUrl().pathname).toBe('/api/v1/autocount/pulls');
    const init = lastInit();
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ entity: 'products' });
    expect(result.job_id).toBe(REVIEW_PULL.job_id);
    expect(result.phase).toBe('review');
    expect((result as any).header).toMatchObject({ companyCode: 'SRT', snapshotId: PRODUCTS_HEADER.snapshotId });
  });
});

describe('getCurrentPull (AC-PL-4)', () => {
  it('S2a: 200 -> the pull', async () => {
    apiFetch.mockResolvedValue(ok(REVIEW_PULL));

    const result = await getCurrentPull('products');

    expect(calledUrl().pathname).toBe('/api/v1/autocount/pulls/current');
    expect(calledUrl().searchParams.get('entity')).toBe('products');
    expect(result?.job_id).toBe(REVIEW_PULL.job_id);
  });

  it('S2b: 404 -> null, never throws', async () => {
    apiFetch.mockResolvedValue(fail(404, { code: 'NOT_FOUND', message: 'No open pull.' }));

    const result = await getCurrentPull('products');

    expect(result).toBeNull();
  });

  it('S2c: 500 -> throws the extracted message', async () => {
    apiFetch.mockResolvedValue(fail(500, { message: 'Server error. Try again or contact support.' }));

    await expect(getCurrentPull('products')).rejects.toThrow();
  });
});

describe('getPull (AC-BD-1)', () => {
  it('S3: GETs /api/v1/autocount/pulls/{id}', async () => {
    apiFetch.mockResolvedValue(ok(REVIEW_PULL));

    const result = await getPull(REVIEW_PULL.job_id);

    expect(calledUrl().pathname).toBe(`/api/v1/autocount/pulls/${REVIEW_PULL.job_id}`);
    expect(result.job_id).toBe(REVIEW_PULL.job_id);
  });
});

describe('getPullRows / confirmPull / comparePull wire shapes (AC-RV-3, AC-PC-1, AC-CM-1)', () => {
  it('S4a: getPullRows uses DataGrid params (page, limit, query) on /rows', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1 }, empty: true }));

    await getPullRows(REVIEW_PULL.job_id, { pageIndex: 2, pageSize: 25, query: 'SRT-1' });

    const url = calledUrl();
    expect(url.pathname).toBe(`/api/v1/autocount/pulls/${REVIEW_PULL.job_id}/rows`);
    expect(url.searchParams.get('page')).toBe('3');
    expect(url.searchParams.get('limit')).toBe('25');
    expect(url.searchParams.get('query')).toBe('SRT-1');
  });

  it('S4b: confirmPull POSTs /confirm', async () => {
    apiFetch.mockResolvedValue(ok({ ...REVIEW_PULL, phase: 'confirmed', apply_job_id: 'apply-1' }));

    await confirmPull(REVIEW_PULL.job_id);

    expect(calledUrl().pathname).toBe(`/api/v1/autocount/pulls/${REVIEW_PULL.job_id}/confirm`);
    expect(lastInit().method).toBe('POST');
  });

  it('S4c: comparePull POSTs {filename, rows} to /compare', async () => {
    apiFetch.mockResolvedValue(
      ok({ summary: { filename: 'my.xlsx', compared_at: '2026-09-20T00:00:00Z', total: 1, matched: 1, different: 0, only_in_excel: 0, only_in_pull: 0 }, differences: [] }),
    );
    const rows = [{ 'Item Code': 'SRT-1' }];

    await comparePull(REVIEW_PULL.job_id, 'my.xlsx', rows);

    expect(calledUrl().pathname).toBe(`/api/v1/autocount/pulls/${REVIEW_PULL.job_id}/compare`);
    const init = lastInit();
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ filename: 'my.xlsx', rows });
  });
});

describe('downloadPullXlsx filename (captain ruling, Phase 3 fix round, V-3)', () => {
  function blobResponse(headers: Record<string, string> = {}) {
    return {
      ok: true,
      status: 200,
      headers: { get: (k: string) => headers[k.toLowerCase()] ?? headers[k] ?? null },
      blob: async () => new Blob(['x']),
    } as unknown as Response;
  }

  /** Captures the `<a download>` element the function creates, appends, clicks and removes -
   *  all synchronously, so there is nothing left in the DOM to query afterwards. */
  function captureDownloadAnchor(): { get: () => HTMLAnchorElement | null } {
    let captured: HTMLAnchorElement | null = null;
    const realCreateElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = realCreateElement(tag);
      if (tag === 'a') captured = el as HTMLAnchorElement;
      return el;
    });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    (URL as unknown as { createObjectURL: () => string }).createObjectURL = () => 'blob:mock';
    (URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = () => {};
    return { get: () => captured };
  }

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('V-3a: the saved filename never contains the job id (no entity known at this layer)', async () => {
    apiFetch.mockResolvedValue(blobResponse());
    const anchor = captureDownloadAnchor();

    await downloadPullXlsx(REVIEW_PULL.job_id);

    const el = anchor.get();
    expect(el).not.toBeNull();
    expect(el!.download).not.toContain(REVIEW_PULL.job_id);
  });

  it('V-3b: uses the server\'s Content-Disposition filename when present', async () => {
    apiFetch.mockResolvedValue(
      blobResponse({ 'content-disposition': 'attachment; filename="autocount-products-pull.xlsx"' }),
    );
    const anchor = captureDownloadAnchor();

    await downloadPullXlsx(REVIEW_PULL.job_id);

    expect(anchor.get()!.download).toBe('autocount-products-pull.xlsx');
  });
});

describe('startPullErrorMessage (AC-PL-6)', () => {
  const CODES = ['PULL_NOT_ENABLED', 'PUSH_ACTIVE', 'TOO_MANY_BUILDS', 'NOT_CONFIGURED', 'UNREACHABLE'];

  it('S5a: maps every known code to a distinct, non-empty message', () => {
    const messages = CODES.map((code) => startPullErrorMessage({ code, message: 'server said something' }));
    expect(messages.every((m) => typeof m === 'string' && m.length > 0)).toBe(true);
    expect(new Set(messages).size).toBe(CODES.length);
  });

  it('S5b: an unknown code falls back to the server message', () => {
    const message = startPullErrorMessage({ code: 'SOMETHING_NEW', message: 'AutoCount said something new.' });
    expect(message).toBe('AutoCount said something new.');
  });
});

describe('SR2 DoD: the Phase 1 mock is gone (AC item 1)', () => {
  it('S6: no file under sorento_crm_frontend/app references USE_MOCK, hasAutocountPullPermissionMock, mockImportJobShim, or the __mocks__ folder, which no longer exists', async () => {
    const fs = await import('node:fs');
    const path = await import('node:path');

    const appRoot = path.resolve(__dirname, '../../../../../../app');

    const mocksDir = path.resolve(__dirname, '../__mocks__');
    expect(fs.existsSync(mocksDir)).toBe(false);

    const offenders: string[] = [];
    const FORBIDDEN = ['USE_MOCK', 'hasAutocountPullPermissionMock', 'mockImportJobShim', "autocount-pull/__mocks__"];

    function walk(dir: string) {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          walk(full);
          continue;
        }
        // Test files legitimately name these strings in prose/mocks (this file's own FORBIDDEN
        // list included) - the DoD is about the app's shipped source, not its tests.
        if (!/\.(ts|tsx)$/.test(entry.name) || /\.test\.(ts|tsx)$/.test(entry.name)) continue;
        const contents = fs.readFileSync(full, 'utf-8');
        for (const needle of FORBIDDEN) {
          if (contents.includes(needle)) offenders.push(`${full}: ${needle}`);
        }
      }
    }

    walk(appRoot);
    expect(offenders).toEqual([]);
  });
});
