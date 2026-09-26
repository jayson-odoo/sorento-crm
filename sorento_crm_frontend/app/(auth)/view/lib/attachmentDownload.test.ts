import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  fetchViewAttachmentBytes,
  toViewPreviewItem,
  viewAttachmentDownloadUrl,
} from './attachmentDownload';

describe('viewAttachmentDownloadUrl', () => {
  it('builds a same-origin byte route keyed on attachment id, carrying the view token', () => {
    expect(viewAttachmentDownloadUrl('complaint', 'att-1', 'tok abc')).toBe(
      '/api/v1/public/view/complaint/attachments/att-1/download?token=tok%20abc',
    );
    expect(viewAttachmentDownloadUrl('stock-inquiry', 'att-2', 'tok')).toBe(
      '/api/v1/public/view/stock-inquiry/attachments/att-2/download?token=tok',
    );
  });
});

describe('toViewPreviewItem', () => {
  it('sets downloadUrl when the attachment carries an attachment_id, even though url is a bare cross-origin CDN link', () => {
    const item = toViewPreviewItem(
      {
        id: 'link-1',
        attachment_id: 'att-1',
        original_filename: 'scan.pdf',
        file_url: 'https://cdn.example.com/scan.pdf',
      },
      'complaint',
      'tok-1',
      'fallback-0',
    );
    expect(item.url).toBe('https://cdn.example.com/scan.pdf');
    expect(item.downloadUrl).toBe(
      '/api/v1/public/view/complaint/attachments/att-1/download?token=tok-1',
    );
  });

  it('leaves downloadUrl unset for a legacy row with no attachment_id', () => {
    const item = toViewPreviewItem(
      { file_url: 'https://cdn.example.com/scan.pdf' },
      'stock-inquiry',
      'tok-1',
      'fallback-0',
    );
    expect(item.downloadUrl).toBeUndefined();
  });
});

describe('fetchViewAttachmentBytes', () => {
  const originalEnv = process.env.NEXT_PUBLIC_API_URL;

  beforeEach(() => {
    delete process.env.NEXT_PUBLIC_API_URL;
  });

  afterEach(() => {
    if (originalEnv === undefined) delete process.env.NEXT_PUBLIC_API_URL;
    else process.env.NEXT_PUBLIC_API_URL = originalEnv;
  });

  it('rejects with no downloadUrl rather than falling back to the cross-origin url', async () => {
    await expect(
      fetchViewAttachmentBytes({ id: '1', name: 'scan.pdf', url: 'https://cdn.example.com/scan.pdf' }),
    ).rejects.toThrow('This attachment has no download route.');
  });

  it('fetches the byte route, never the cross-origin CDN url (jsdom defaults to :3000, so this exercises the dev fallback to :8000, same as the portal client)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal('fetch', fetchMock);

    await fetchViewAttachmentBytes({
      id: '1',
      name: 'scan.pdf',
      url: 'https://cdn.example.com/scan.pdf',
      downloadUrl: '/api/v1/public/view/complaint/attachments/att-1/download?token=tok-1',
    });

    const [calledUrl] = fetchMock.mock.calls[0];
    expect(calledUrl).not.toBe('https://cdn.example.com/scan.pdf');
    expect(calledUrl).toMatch(
      /\/api\/v1\/public\/view\/complaint\/attachments\/att-1\/download\?token=tok-1$/,
    );
    vi.unstubAllGlobals();
  });

  it('goes straight to the API host when NEXT_PUBLIC_API_URL is set, bypassing the Next.js public catch-all', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'https://api.example.com';
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal('fetch', fetchMock);

    await fetchViewAttachmentBytes({
      id: '1',
      name: 'scan.pdf',
      url: 'https://cdn.example.com/scan.pdf',
      downloadUrl: '/api/v1/public/view/complaint/attachments/att-1/download?token=tok-1',
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.com/api/v1/public/view/complaint/attachments/att-1/download?token=tok-1',
    );
    vi.unstubAllGlobals();
  });
});
