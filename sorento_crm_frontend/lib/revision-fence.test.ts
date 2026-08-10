/**
 * The revision fence, frontend half (UAC `portal-submission-revisions` C-bis).
 *
 * The unit here is the URL classifier plus the registry: which requests are
 * fenced, what we remember off a read, and what a refusal does. The end-to-end
 * "the header actually goes out on the wire" assertion lives in
 * `lib/api.revisionFence.test.ts`, against `apiFetch` itself.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

import {
  REVISION_HEADER,
  clearRememberedRevisions,
  fencedWriteEntityId,
  handleRevisionConflict,
  harvestRevisions,
  isFencedReadPath,
  registerRevisionStaleHandler,
  rememberRevision,
  rememberedRevision,
} from './revision-fence';

const SI = '11111111-2222-3333-4444-555555555555';
const PR = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';

beforeEach(() => {
  clearRememberedRevisions();
  registerRevisionStaleHandler(null);
});

describe('header name', () => {
  it('matches the backend spelling exactly', () => {
    expect(REVISION_HEADER).toBe('X-Revision-No');
  });
});

describe('fencedWriteEntityId', () => {
  it('matches a write against one record, on every fenced collection', () => {
    expect(
      fencedWriteEntityId(`/api/v1/procurement/stock-inquiries/${SI}`, 'PUT'),
    ).toBe(SI);
    expect(
      fencedWriteEntityId(`/api/v1/procurement/purchase-requests/${PR}`, 'DELETE'),
    ).toBe(PR);
    expect(
      fencedWriteEntityId(`/api/v1/complaints-management/complaints/${SI}`, 'PUT'),
    ).toBe(SI);
  });

  it('matches the action sub-paths, which is where most of the 34 routes are', () => {
    for (const suffix of [
      'update-and-reply',
      'project-sales-approve',
      'purchasing-reject',
      'void',
      'reopen',
      'attachments',
      'response-attachments',
    ]) {
      expect(
        fencedWriteEntityId(`/api/v1/procurement/stock-inquiries/${SI}/${suffix}`, 'POST'),
      ).toBe(SI);
    }
  });

  it('works on the absolute URL local dev produces', () => {
    expect(
      fencedWriteEntityId(
        `http://localhost:8000/api/v1/procurement/stock-inquiries/${SI}/void`,
        'POST',
      ),
    ).toBe(SI);
  });

  it('ignores the query string', () => {
    expect(
      fencedWriteEntityId(`/api/v1/procurement/stock-inquiries/${SI}?x=1`, 'PUT'),
    ).toBe(SI);
  });

  it('does not fence reads', () => {
    expect(fencedWriteEntityId(`/api/v1/procurement/stock-inquiries/${SI}`, 'GET')).toBeNull();
    expect(fencedWriteEntityId(`/api/v1/procurement/stock-inquiries/${SI}`)).toBeNull();
  });

  it('does not fence a link-keyed sub-resource, whose id is not the entity', () => {
    expect(
      fencedWriteEntityId(`/api/v1/procurement/stock-inquiries/attachments/${SI}`, 'DELETE'),
    ).toBeNull();
    expect(
      fencedWriteEntityId(
        `/api/v1/procurement/stock-inquiries/response-attachments/${SI}`,
        'DELETE',
      ),
    ).toBeNull();
  });

  it('does not fence the collection itself, nor an unrelated resource', () => {
    expect(fencedWriteEntityId('/api/v1/procurement/stock-inquiries', 'POST')).toBeNull();
    expect(fencedWriteEntityId('/api/v1/procurement/stock-inquiries/bulk', 'DELETE')).toBeNull();
    expect(fencedWriteEntityId(`/api/v1/master-data/products/${SI}`, 'PUT')).toBeNull();
  });

  /**
   * The sub-paths the backend deliberately leaves open. Stamping the header here
   * would be worse than noise: it makes `fencedEntityId` non-null, so ANY 409 from
   * one of these reads as "someone revised this record" and triggers a blanket
   * cache invalidation for a conflict that has nothing to do with revisions.
   */
  it('does not fence a sub-route the backend leaves open', () => {
    const open: [string, string][] = [
      // AC O2: messaging a contact about a revised record must keep working.
      ['/api/v1/procurement/stock-inquiries', 'conversation/send-message'],
      ['/api/v1/procurement/stock-inquiries', 'conversation/template-message'],
      ['/api/v1/procurement/stock-inquiries', 'view-link'],
      ['/api/v1/procurement/stock-inquiries', 'export/pdf'],
      ['/api/v1/procurement/purchase-requests', 'conversation/send-message'],
      ['/api/v1/procurement/purchase-requests', 'view-link'],
      ['/api/v1/procurement/purchase-requests', 'export/pdf'],
      ['/api/v1/complaints-management/complaints', 'conversation/send-message'],
      ['/api/v1/complaints-management/complaints', 'sync-assignee'],
      ['/api/v1/complaints-management/complaints', 'export/pdf'],
    ];
    for (const [root, suffix] of open) {
      expect(fencedWriteEntityId(`${root}/${SI}/${suffix}`, 'POST'), suffix).toBeNull();
    }
  });

  it('does not fence a sub-route nobody has taught it about yet', () => {
    // A route added upstream starts out unsent. Absent means unfenced, which is the
    // honest answer until the allowlist learns about it - and
    // `revision-fence.contract.test.ts` is what makes someone teach it.
    expect(
      fencedWriteEntityId(`/api/v1/procurement/stock-inquiries/${SI}/brand-new-action`, 'POST'),
    ).toBeNull();
  });
});

describe('isFencedReadPath', () => {
  it('covers the list and the detail, so a row action is fenced too', () => {
    expect(isFencedReadPath('/api/v1/procurement/stock-inquiries?page=1', 'GET')).toBe(true);
    expect(isFencedReadPath(`/api/v1/procurement/stock-inquiries/${SI}`, 'GET')).toBe(true);
  });

  it('excludes sub-resources, whose rows carry a revision_no against another id', () => {
    expect(
      isFencedReadPath(`/api/v1/procurement/stock-inquiries/${SI}/revisions`, 'GET'),
    ).toBe(false);
    expect(isFencedReadPath('/api/v1/procurement/stock-inquiries/neighbours', 'GET')).toBe(false);
  });

  it('excludes writes - only a read tells us what was on screen', () => {
    expect(isFencedReadPath(`/api/v1/procurement/stock-inquiries/${SI}`, 'PUT')).toBe(false);
  });
});

describe('the registry', () => {
  it('remembers what a read showed', () => {
    rememberRevision(SI, 2);
    expect(rememberedRevision(SI)).toBe(2);
  });

  it('reports null for a record never read, so no header is sent', () => {
    expect(rememberedRevision(SI)).toBeNull();
  });

  it('keeps the highest seen - a stale list must not undo a fresh detail read', () => {
    rememberRevision(SI, 3);
    rememberRevision(SI, 1);
    expect(rememberedRevision(SI)).toBe(3);
  });

  it('ignores a missing or unusable revision', () => {
    rememberRevision(SI, null);
    rememberRevision(SI, undefined);
    rememberRevision(SI, 'two');
    expect(rememberedRevision(SI)).toBeNull();
  });

  it('records revision 0, which is a real value and not "unknown"', () => {
    rememberRevision(SI, 0);
    expect(rememberedRevision(SI)).toBe(0);
  });
});

describe('harvestRevisions', () => {
  it('reads one record off a detail payload', () => {
    harvestRevisions({ id: SI, inquiry_number: 'SI-26-0184', revision_no: 4 });
    expect(rememberedRevision(SI)).toBe(4);
  });

  it('reads a page of rows off a list payload', () => {
    harvestRevisions({ items: [{ id: SI, revision_no: 1 }, { id: PR, revision_no: 7 }] });
    expect(rememberedRevision(SI)).toBe(1);
    expect(rememberedRevision(PR)).toBe(7);
  });

  it('reads a bare array', () => {
    harvestRevisions([{ id: SI, revision_no: 2 }]);
    expect(rememberedRevision(SI)).toBe(2);
  });

  it('does not walk into nested objects, so a timeline cannot poison the map', () => {
    harvestRevisions({ id: PR, revision_no: 1, latest: { id: SI, revision_no: 99 } });
    expect(rememberedRevision(PR)).toBe(1);
    expect(rememberedRevision(SI)).toBeNull();
  });

  it('shrugs off a payload that is not an object', () => {
    expect(() => harvestRevisions(null)).not.toThrow();
    expect(() => harvestRevisions('nope')).not.toThrow();
  });
});

describe('handleRevisionConflict', () => {
  const SENTENCE =
    'This stock inquiry was revised while you were working on it. Reload to see revision 2.';

  function conflict(): Response {
    return new Response(JSON.stringify({ detail: SENTENCE }), {
      status: 409,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  it('refreshes the record so the user is not left on the superseded version', async () => {
    const onStale = vi.fn();
    registerRevisionStaleHandler(onStale);
    await handleRevisionConflict(SI, conflict());
    expect(onStale).toHaveBeenCalledWith(SI);
  });

  it('hands back the server sentence under both keys the services read', async () => {
    const normalized = await handleRevisionConflict(SI, conflict());
    expect(normalized.status).toBe(409);
    const body = await normalized.json();
    // `extractApiError` and `err.detail` and `err.message` must all land on it.
    expect(body.detail).toBe(SENTENCE);
    expect(body.message).toBe(SENTENCE);
  });

  it('still reports the refusal when the refresh itself blows up', async () => {
    registerRevisionStaleHandler(() => {
      throw new Error('query client is gone');
    });
    const normalized = await handleRevisionConflict(SI, conflict());
    expect((await normalized.json()).detail).toBe(SENTENCE);
  });
});
