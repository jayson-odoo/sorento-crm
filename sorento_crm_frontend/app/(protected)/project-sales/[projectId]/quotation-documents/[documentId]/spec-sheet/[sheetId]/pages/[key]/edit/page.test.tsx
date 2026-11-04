import { describe, expect, it, vi } from 'vitest';

const redirect = vi.fn((url: string) => {
  throw new Error(`REDIRECT:${url}`);
});
vi.mock('next/navigation', () => ({ redirect: (url: string) => redirect(url) }));

import EditProjectQuotationSpecSheetPage from './page';

describe('the old Edit spec sheet page route', () => {
  // The reader IS the editor now: an old link lands on the reader, scrolled to that page.
  it.each([
    ['set:5f96ff63-e124-4518-a41f-777f15963ceb'],
    ['code:AB/12,X'],
    ['cover'],
  ])('redirects %s to the reader at that page', async (key) => {
    await expect(
      EditProjectQuotationSpecSheetPage({
        params: Promise.resolve({ projectId: 'p', documentId: 'd', sheetId: 's', key: encodeURIComponent(key) }),
      }),
    ).rejects.toThrow('REDIRECT:');
    expect(redirect).toHaveBeenLastCalledWith(
      `/project-sales/p/quotation-documents/d/spec-sheet/s?page=${encodeURIComponent(key)}`,
    );
  });
});
