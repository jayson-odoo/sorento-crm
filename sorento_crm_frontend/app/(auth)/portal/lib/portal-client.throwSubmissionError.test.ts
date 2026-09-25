/**
 * #1232 blocking 3: `throwSubmissionError` was reading the wrong shape - it
 * called `extractApiError` first (which, for a plain string `detail`, returns
 * `detail` itself rather than the human `message` - `extractApiError`'s own
 * contract), then tried to clone an already-consumed body for `code`/`detail`,
 * so the dealer saw the toast "line:0" instead of "Unit price is required."
 * This test feeds `saveDraft`/`submitDraft` the EXACT wire body the global
 * handler emits for an `AppException` (`app/main.py`'s `app_exception_handler`
 * returns `exc.detail` verbatim - see `app/services/error_handler.py`'s
 * `AppException.__init__`), not a hand-built error shape.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { saveDraft, submitDraft, reviseSubmission } from './portal-client';

const REAL_WIRE_BODY = {
  message: 'Unit price is required.',
  detail: 'line:0',
  code: 'SPONSORSHIP_UNIT_PRICE_REQUIRED',
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('throwSubmissionError - real AppException wire body (#1232 blocking 3)', () => {
  it('submitDraft surfaces the server message, not the line:<index> detail token', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(422, REAL_WIRE_BODY));

    await expect(
      submitDraft('sponsorship_form', 'sub-1'),
    ).rejects.toMatchObject({
      message: 'Unit price is required.',
      code: 'SPONSORSHIP_UNIT_PRICE_REQUIRED',
      fields: ['line:0'],
    });
  });

  it('saveDraft surfaces the server message, not the line:<index> detail token', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(422, REAL_WIRE_BODY));

    await expect(
      saveDraft('sponsorship_form', {}, [{ item_code: 'X', quantity: 2 }]),
    ).rejects.toMatchObject({
      message: 'Unit price is required.',
      code: 'SPONSORSHIP_UNIT_PRICE_REQUIRED',
      fields: ['line:0'],
    });
  });

  it('falls back to extractApiError for a body with no top-level message (plain FastAPI 500)', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(500, { detail: 'Server error. Try again or contact support.' }),
    );

    await expect(submitDraft('sponsorship_form', 'sub-1')).rejects.toMatchObject({
      message: 'Server error. Try again or contact support.',
      code: null,
    });
  });

  it('reviseSubmission surfaces the server message, not the line:<index> detail token', async () => {
    // reviseSubmission was routed through the plain `unwrap` helper, which
    // reads the flat wire body's `detail` token as the message - the same bug
    // already fixed here for saveDraft/submitDraft.
    vi.mocked(fetch).mockResolvedValue(jsonResponse(422, REAL_WIRE_BODY));

    await expect(
      reviseSubmission('sponsorship_form', 'sub-1', {
        reason: 'Corrected the price',
        expectedRevisionNo: 0,
        fields: {},
        products: [{ item_code: 'X', quantity: 2 }],
      }),
    ).rejects.toMatchObject({
      message: 'Unit price is required.',
      code: 'SPONSORSHIP_UNIT_PRICE_REQUIRED',
      fields: ['line:0'],
    });
  });

  it('multiple line refusals split the CSV detail into separate field tokens', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(422, {
        message: 'Unit price is required.',
        detail: 'line:0,line:2',
        code: 'SPONSORSHIP_UNIT_PRICE_REQUIRED',
      }),
    );

    await expect(submitDraft('sponsorship_form', 'sub-1')).rejects.toMatchObject({
      fields: ['line:0', 'line:2'],
    });
  });
});
