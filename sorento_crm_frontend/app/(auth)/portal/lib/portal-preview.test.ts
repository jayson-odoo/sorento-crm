/**
 * Portal preview wiring (UAC-portal-submission-revisions I2 / I2a / I5).
 *
 * The portal has no NextAuth session, so the shared modal's default byte
 * reader (`apiFetch`) 401s there. These pin the two things that make the
 * escape hatch correct: the route is keyed on attachment_id (not link_id),
 * and the bytes travel with the portal token instead of apiFetch.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetchMock = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}));

import { portalFetchBytes, toPreviewItem } from './portal-preview';
import { writePortalToken, clearPortalToken, type PortalAttachment } from './portal-client';

function attachment(over: Partial<PortalAttachment> = {}): PortalAttachment {
  return {
    link_id: 'link-1',
    attachment_id: 'att-1',
    filename: 'quote.pdf',
    size: 4096,
    url: 'https://cdn.example.com/quote.pdf',
    content_type: 'application/pdf',
    ...over,
  };
}

beforeEach(() => {
  apiFetchMock.mockReset();
  clearPortalToken();
});

describe('toPreviewItem', () => {
  it('keys the bytes route on attachment_id, not link_id', () => {
    const item = toPreviewItem(attachment());
    // link_id stays the row identity; the route must not use it (I2a) - a
    // revision unlinks removed files, so a link-keyed URL would 404 on exactly
    // the historical attachments.
    expect(item.id).toBe('link-1');
    expect(item.downloadUrl).toBe('/api/v1/public/portal/attachments/att-1/download');
  });

  it('carries the CDN url for inline rendering and a readable name', () => {
    const item = toPreviewItem(attachment({ filename: null }));
    expect(item.url).toBe('https://cdn.example.com/quote.pdf');
    expect(item.name).toBe('Attachment');
    expect(item.sizeBytes).toBe(4096);
  });
});

describe('portalFetchBytes', () => {
  it('reads bytes with the portal token and never through apiFetch', async () => {
    writePortalToken('tok-123');
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal('fetch', fetchMock);

    await portalFetchBytes(toPreviewItem(attachment()));

    expect(apiFetchMock).not.toHaveBeenCalled();
    const [url, init] = fetchMock.mock.calls[0];
    // Goes to the API host, NOT the same-origin Next proxy - that proxy
    // re-serializes every response as JSON and would return `{}` for bytes.
    expect(url).toMatch(
      /^https?:\/\/[^/]+\/api\/v1\/public\/portal\/attachments\/att-1\/download$/,
    );
    expect(new Headers(init.headers).get('X-Portal-Token')).toBe('tok-123');
  });

  it('rejects rather than falling back to an unauthenticated URL', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await expect(
      portalFetchBytes({ id: 'x', name: 'x.pdf', url: 'blob:local' }),
    ).rejects.toThrow(/no download route/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
