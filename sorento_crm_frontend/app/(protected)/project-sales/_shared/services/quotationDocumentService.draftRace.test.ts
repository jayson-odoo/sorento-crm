/**
 * QUOTE-AUTOSAVE crew pass (11 Nov): "Continue editing opened the saved values without the draft".
 *
 * Leaving the form flushes its last edit (a PUT); Continue editing a moment later OPENS the draft
 * (a POST that also claims it for the new tab). If the open overtakes the flush, the form opens on
 * the old draft and the flush then lands under a lapsed claim. Opening must wait for any draft
 * write this browser still has on its way for the same draft.
 */
import { describe, expect, it, vi } from 'vitest';

const calls: string[] = [];
const pending: Array<(response: Response) => void> = [];
vi.mock('@/lib/api', () => ({
  apiFetch: (url: string, init?: RequestInit) => {
    calls.push(`${init?.method ?? 'GET'} ${url}`);
    return new Promise<Response>((resolve) => pending.push(resolve));
  },
}));

import {
  openQuotationFormDraft,
  saveQuotationFormDraft,
  type QuotationFormState,
} from './quotationDocumentService';

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });

const state = {
  v: 1,
  header: { your_ref: 'typed then left' },
  letter: {},
  scopes: [],
  staged: {},
  removedIds: [],
  total: '0',
} as QuotationFormState;

describe('opening a draft waits for this browser\'s draft write on its way', () => {
  it('the open is not sent until the in-flight save of the same draft has answered', async () => {
    calls.length = 0;
    pending.length = 0;
    const save = saveQuotationFormDraft('p1', 'd1', state, 'tok-old');
    const open = openQuotationFormDraft('p1', 'd1');
    await Promise.resolve();
    await Promise.resolve();
    expect(calls).toEqual(['PUT /api/v1/project-sales/projects/p1/quotation-documents/d1/form-draft']);

    pending[0](json({ updated_at: '2026-11-11T01:00:00' }));
    await save;
    await vi.waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1]).toBe('POST /api/v1/project-sales/projects/p1/quotation-documents/d1/form-draft/open');
    pending[1](json({ draft_id: 'x', token: 'tok-new', doc: state, updated_at: null, updated_by_name: null }));
    expect((await open).doc?.header.your_ref).toBe('typed then left');
  });

  it('a failed save does not hold the open back', async () => {
    calls.length = 0;
    pending.length = 0;
    const save = saveQuotationFormDraft('p1', 'd2', state, 'tok').catch(() => undefined);
    const open = openQuotationFormDraft('p1', 'd2');
    pending[0](new Response('{"message":"down"}', { status: 503, headers: { 'Content-Type': 'application/json' } }));
    await save;
    await vi.waitFor(() => expect(calls).toHaveLength(2));
    pending[1](json({ draft_id: 'x', token: 't', doc: null, updated_at: null, updated_by_name: null }));
    await open;
  });

  it('a different draft is not held back', async () => {
    calls.length = 0;
    pending.length = 0;
    void saveQuotationFormDraft('p1', 'd3', state, 'tok');
    void openQuotationFormDraft('p1', 'd4');
    await vi.waitFor(() => expect(calls).toHaveLength(2));
  });
});
