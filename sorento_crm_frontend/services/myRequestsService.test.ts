/**
 * PORTAL-P4-REQUESTS S-FE0 (P4-11..P4-17): `services/myRequestsService.ts` is the CRM-session client for
 * `/api/v1/my-requests/...`. Same function names, arguments, paths and bodies as the portal client
 * (`app/(auth)/portal/lib/portal-client.ts`), but over the CRM session (`apiFetch` from `@/lib/api`, errors via
 * `extractApiError`) instead of the portal token, and under `/api/v1/my-requests` instead of `/api/v1/public/portal`.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import * as svc from './myRequestsService';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

const last = () => {
  const [url, init] = apiFetch.mock.calls[apiFetch.mock.calls.length - 1] as [string, RequestInit | undefined];
  return { url, method: (init?.method ?? 'GET').toUpperCase(), body: init?.body, init };
};

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue(json({ id: 'x', items: [] }));
});

describe('myRequestsService paths and bodies', () => {
  it('saveDraft without an id POSTs /submissions/{kind} with {fields, products}', async () => {
    await svc.saveDraft('stock_inquiry', { product_code: 'A' }, [{ q: 1 }]);
    const c = last();
    expect(c.url).toBe('/api/v1/my-requests/submissions/stock_inquiry');
    expect(c.method).toBe('POST');
    expect(JSON.parse(c.body as string)).toEqual({ fields: { product_code: 'A' }, products: [{ q: 1 }] });
  });

  it('saveDraft with an id PUTs /submissions/{kind}/{id}', async () => {
    await svc.saveDraft('stock_inquiry', { product_code: 'A' }, undefined, 'si-1');
    expect(last().url).toBe('/api/v1/my-requests/submissions/stock_inquiry/si-1');
    expect(last().method).toBe('PUT');
  });

  it('submitDraft POSTs /submissions/{kind}/{id}/submit', async () => {
    await svc.submitDraft('stock_inquiry', 'si-1', { product_code: 'B' });
    expect(last().url).toBe('/api/v1/my-requests/submissions/stock_inquiry/si-1/submit');
    expect(last().method).toBe('POST');
    expect(JSON.parse(last().body as string)).toEqual({ fields: { product_code: 'B' } });
  });

  it('deleteDraftSubmission DELETEs /submissions/{kind}/{id} and accepts 204', async () => {
    apiFetch.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(svc.deleteDraftSubmission('stock_inquiry', 'si-1')).resolves.toBeUndefined();
    expect(last().url).toBe('/api/v1/my-requests/submissions/stock_inquiry/si-1');
    expect(last().method).toBe('DELETE');
  });

  it('reviseSubmission POSTs .../revise with reason, expected_revision_no, fields', async () => {
    apiFetch.mockResolvedValue(json({ submission: { id: 'si-1' }, revision: {}, revision_no: 1 }));
    await svc.reviseSubmission('stock_inquiry', 'si-1', {
      reason: 'wrong qty',
      expectedRevisionNo: 0,
      fields: { quantity: '5' },
    });
    expect(last().url).toBe('/api/v1/my-requests/submissions/stock_inquiry/si-1/revise');
    expect(last().method).toBe('POST');
    expect(JSON.parse(last().body as string)).toMatchObject({
      reason: 'wrong qty',
      expected_revision_no: 0,
      fields: { quantity: '5' },
    });
  });

  it('saveRevisionDraft PUTs and discardRevisionDraft DELETEs .../revision-draft', async () => {
    apiFetch.mockResolvedValue(json({ stale: false, fields: {} }));
    await svc.saveRevisionDraft('stock_inquiry', 'si-1', { baseRevisionNo: 0, fields: {} });
    expect(last().url).toBe('/api/v1/my-requests/submissions/stock_inquiry/si-1/revision-draft');
    expect(last().method).toBe('PUT');
    apiFetch.mockResolvedValue(new Response(null, { status: 204 }));
    await svc.discardRevisionDraft('stock_inquiry', 'si-1');
    expect(last().url).toBe('/api/v1/my-requests/submissions/stock_inquiry/si-1/revision-draft');
    expect(last().method).toBe('DELETE');
  });

  it('fetchRequestorOptions GETs /requestor-options?q= and returns {items, hasMore}', async () => {
    apiFetch.mockResolvedValue(json({ items: [{ id: 'c1', name: 'Ann' }], has_more: true }));
    const out = await svc.fetchRequestorOptions('an');
    expect(last().url).toBe('/api/v1/my-requests/requestor-options?q=an');
    expect(out).toEqual({ items: [{ id: 'c1', name: 'Ann' }], hasMore: true });
  });

  it('fetchSubmission and fetchRevisions GET under /submissions/{kind}/{id}', async () => {
    apiFetch.mockResolvedValue(json({ id: 'si-1' }));
    await svc.fetchSubmission('stock_inquiry', 'si-1');
    expect(last().url).toBe('/api/v1/my-requests/submissions/stock_inquiry/si-1');
    apiFetch.mockResolvedValue(json({ items: [] }));
    await svc.fetchRevisions('stock_inquiry', 'si-1');
    expect(last().url).toBe('/api/v1/my-requests/submissions/stock_inquiry/si-1/revisions');
  });

  it('comments: GET, multipart POST, PATCH, DELETE', async () => {
    await svc.fetchSubmissionComments('stock_inquiry', 'si-1');
    expect(last().url).toBe('/api/v1/my-requests/submissions/stock_inquiry/si-1/comments');
    apiFetch.mockResolvedValue(json({ comment: { id: 'cm1', body: 'hi' }, delivery: 'sent' }));
    await svc.postSubmissionComment('stock_inquiry', 'si-1', 'hi', []);
    expect(last().url).toBe('/api/v1/my-requests/submissions/stock_inquiry/si-1/comments');
    expect(last().method).toBe('POST');
    expect(last().body).toBeInstanceOf(FormData);
    expect((last().body as FormData).get('body')).toBe('hi');
    apiFetch.mockResolvedValue(new Response(null, { status: 204 }));
    await svc.editSubmissionComment('stock_inquiry', 'si-1', 'cm1', 'edited');
    expect(last().url).toBe('/api/v1/my-requests/submissions/stock_inquiry/si-1/comments/cm1');
    expect(last().method).toBe('PATCH');
    await svc.deleteSubmissionComment('stock_inquiry', 'si-1', 'cm1');
    expect(last().method).toBe('DELETE');
  });

  it('attachments: multipart POST /attachments, DELETE /attachments/{link}, download url', async () => {
    apiFetch.mockResolvedValue(json({ id: 'a1' }));
    await svc.uploadAttachment('stock_inquiry', 'si-1', new File(['x'], 'p.png', { type: 'image/png' }));
    expect(last().url).toBe('/api/v1/my-requests/attachments');
    expect(last().method).toBe('POST');
    const form = last().body as FormData;
    expect(form.get('kind')).toBe('stock_inquiry');
    expect(form.get('submission_id')).toBe('si-1');
    apiFetch.mockResolvedValue(new Response(null, { status: 204 }));
    await svc.deleteAttachment('link-1');
    expect(last().url).toBe('/api/v1/my-requests/attachments/link-1');
    expect(last().method).toBe('DELETE');
    expect(svc.myRequestsAttachmentDownloadUrl('att-1')).toBe('/api/v1/my-requests/attachments/att-1/download');
  });

  it('a non-2xx surfaces the server message (extractApiError), not a generic one', async () => {
    apiFetch.mockResolvedValue(json({ detail: 'Only drafts can be deleted.' }, 409));
    await expect(svc.deleteDraftSubmission('stock_inquiry', 'si-1')).rejects.toThrow('Only drafts can be deleted.');
  });
});
