/**
 * ============================================================================
 * SCM - outstanding-orders upload channel, feature service (TDD: written first)
 * ============================================================================
 * Layering: OutstandingUploadDialog -> THIS service -> lib/api-client -> backend.
 *
 * Pins the wire contract against the already-built backend
 * (`app/api/v1/scm/outstanding_import.py`):
 *
 *   POST /api/v1/scm/outstanding/{kind}/preview   writes NOTHING, returns the diff
 *   POST /api/v1/scm/outstanding/{kind}/apply     QUEUES the write, returns the job
 *
 *   kind = 'sales-orders' | 'purchase-orders'
 *   multipart body, single field named exactly "file"
 *
 * Both steps refuse a session with no single active company, with the same message: the
 * order books are owned tables, and a diff computed across every company is about the wrong
 * company's products.
 *
 * SCM services call `apiFetch('/api/v1/scm/...')` with the version segment spelled
 * out (see reorderRunService) - `lib/api.ts` has no `/api/scm` rewrite entry, so a
 * short path would go to Next.js and 404.
 * ============================================================================
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  previewOutstandingImport,
  applyOutstandingImport,
} from './outstandingImportService';

function xlsx(name = 'outstanding-so.xlsx'): File {
  return new File([new Uint8Array(8)], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

function ok(body: unknown) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function fail(status: number, body: unknown) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function calledUrl(): URL {
  const calls = apiFetch.mock.calls;
  return new URL(String(calls[calls.length - 1][0]), 'http://x');
}

function lastInit(): RequestInit {
  const calls = apiFetch.mock.calls;
  return (calls[calls.length - 1][1] ?? {}) as RequestInit;
}

const PREVIEW_BODY = {
  doc_type: 'outstanding_so',
  ok: true,
  scope_documents: ['SO397450'],
  counts: {
    added: 1,
    qty_changed: 0,
    date_moved: 2,
    date_and_qty_changed: 0,
    closed: 0,
    unchanged: 412,
  },
  total_rows: 415,
  unmapped_headers: ['Salesman'],
  missing_columns: [],
  row_problems: [{ row_number: 42, reason: 'quantity is not a number', value: 'N/A' }],
  resolution_issues: [
    {
      row_number: 87,
      field: 'item_code',
      value: 'SRTWC-XXX',
      reason: 'no product with this code',
    },
  ],
  samples: {
    date_moved: [
      {
        doc_number: 'SO397450',
        item_code: 'SRTWC8613-RL',
        location: 'WH-KL',
        qty_before: 135,
        qty_after: 135,
        date_before: '2026-07-01',
        date_after: '2026-07-15',
        days_moved: 14,
        label: 'Tuju Residence',
      },
    ],
  },
};

beforeEach(() => apiFetch.mockReset());

describe('outstandingImportService - preview', () => {
  it('POSTs the file as multipart field "file" to the sales-orders preview route', async () => {
    apiFetch.mockResolvedValue(ok(PREVIEW_BODY));
    const file = xlsx();

    await previewOutstandingImport('sales-orders', file);

    expect(calledUrl().pathname).toBe('/api/v1/scm/outstanding/sales-orders/preview');
    const init = lastInit();
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get('file')).toBe(file);
  });

  it('never sets Content-Type by hand - the browser owns the multipart boundary', async () => {
    apiFetch.mockResolvedValue(ok(PREVIEW_BODY));
    await previewOutstandingImport('sales-orders', xlsx());

    const headers = (lastInit().headers ?? {}) as Record<string, string>;
    const keys = Object.keys(headers).map((k) => k.toLowerCase());
    expect(keys).not.toContain('content-type');
  });

  it('routes purchase-orders to its own kind segment', async () => {
    apiFetch.mockResolvedValue(ok({ ...PREVIEW_BODY, doc_type: 'outstanding_po' }));
    await previewOutstandingImport('purchase-orders', xlsx('outstanding-po.xlsx'));

    expect(calledUrl().pathname).toBe('/api/v1/scm/outstanding/purchase-orders/preview');
  });

  it('returns the preview body verbatim, including counts.unchanged and the problem lists', async () => {
    apiFetch.mockResolvedValue(ok(PREVIEW_BODY));
    const preview = await previewOutstandingImport('sales-orders', xlsx());

    expect(preview.ok).toBe(true);
    expect(preview.counts.unchanged).toBe(412);
    expect(preview.scope_documents).toEqual(['SO397450']);
    expect(preview.unmapped_headers).toEqual(['Salesman']);
    expect(preview.row_problems[0]).toMatchObject({ row_number: 42, value: 'N/A' });
    expect(preview.resolution_issues[0]).toMatchObject({ row_number: 87, value: 'SRTWC-XXX' });
    expect(preview.samples.date_moved?.[0]).toMatchObject({
      date_before: '2026-07-01',
      date_after: '2026-07-15',
      days_moved: 14,
    });
  });

  it('resolves (does NOT throw) on a 200 carrying ok:false + missing_columns', async () => {
    // The backend deliberately returns 200 here so the screen can name the columns.
    apiFetch.mockResolvedValue(
      ok({
        doc_type: 'outstanding_so',
        ok: false,
        scope_documents: [],
        counts: {},
        total_rows: 0,
        unmapped_headers: [],
        missing_columns: ['required_date'],
        row_problems: [],
        resolution_issues: [],
        samples: {},
      }),
    );

    const preview = await previewOutstandingImport('sales-orders', xlsx());
    expect(preview.ok).toBe(false);
    expect(preview.missing_columns).toEqual(['required_date']);
  });

  it('throws the extracted backend message on a non-2xx', async () => {
    apiFetch.mockResolvedValue(
      fail(400, { detail: 'Invalid file type: notes.txt. Upload .xlsx.' }),
    );

    await expect(previewOutstandingImport('sales-orders', xlsx('notes.txt'))).rejects.toThrow(
      'Invalid file type: notes.txt. Upload .xlsx.',
    );
  });

  it('surfaces the single-company refusal, which preview makes too', async () => {
    // Preview is refused at the same scope apply runs at: read across every company the
    // item codes resolve to the wrong company's products and the diff is untrue.
    apiFetch.mockResolvedValue(
      fail(400, { detail: 'Select a single company before uploading the order book.' }),
    );

    await expect(previewOutstandingImport('sales-orders', xlsx())).rejects.toThrow(
      'Select a single company before uploading the order book.',
    );
  });
});

describe('outstandingImportService - apply', () => {
  /**
   * The 202 body, and the whole body. Apply QUEUES the write, so the counts do not exist
   * when the request answers - they land on the job, under `result.upload`. A test still
   * asserting `applied` here would be pinning a response no route returns.
   */
  const QUEUED = {
    message: 'Order book upload queued.',
    job_id: 'e2c3a5f0-1c22-4f77-9b3a-6b8a0a1d5f11',
    id: '9f9c7b1e-3f0a-4a2e-8a4e-5c6d7e8f9a0b',
  };

  it('POSTs the same file as multipart field "file" to the apply route', async () => {
    apiFetch.mockResolvedValue(ok(QUEUED));
    const file = xlsx();

    const result = await applyOutstandingImport('sales-orders', file);

    expect(calledUrl().pathname).toBe('/api/v1/scm/outstanding/sales-orders/apply');
    expect(lastInit().method).toBe('POST');
    expect((lastInit().body as FormData).get('file')).toBe(file);
    // The job to watch, not the outcome: the outcome is computed on the worker.
    expect(result).toEqual(QUEUED);
  });

  it('throws the extracted backend message when the session has no single company', async () => {
    // The only 400 left on this route. An unreadable file no longer fails the request - it
    // fails the JOB, because the reading happens on the worker - so this refusal, which
    // happens before any job row exists, is the one the dialog has to render.
    apiFetch.mockResolvedValue(
      fail(400, { detail: 'Select a single company before uploading the order book.' }),
    );

    await expect(applyOutstandingImport('sales-orders', xlsx())).rejects.toThrow(
      'Select a single company before uploading the order book.',
    );
  });
});
