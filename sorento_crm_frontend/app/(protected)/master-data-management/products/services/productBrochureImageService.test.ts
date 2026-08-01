/**
 * The one place the brochure-image flag is written.
 *
 * There were two of these for a while - one here, one under dealer-kit - hitting
 * the same two endpoints with different URL spellings and different failure
 * messages. Both spellings work through the api rewrite table, which is what
 * kept the drift invisible. These tests pin the single home and let the dealer
 * kit's own module be checked for the absence of a second one.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { setBrochureImage, clearBrochureImage } from './productBrochureImageService';

const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

function ok(body: unknown = { productId: 'prod-1', chosenAttachmentId: 'att-1' }) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

beforeEach(() => {
  mockApiFetch.mockReset();
  mockApiFetch.mockResolvedValue(ok());
});

describe('productBrochureImageService', () => {
  it('puts the chosen attachment on the product', async () => {
    await setBrochureImage('prod-1', 'att-1');

    const [url, init] = mockApiFetch.mock.calls[0];
    expect(String(url)).toBe(
      '/api/v1/master-data/product-attachments/brochure-images/prod-1',
    );
    expect(init).toMatchObject({ method: 'PUT' });
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ attachment_id: 'att-1' });
  });

  it('deletes the choice when it is cleared', async () => {
    mockApiFetch.mockResolvedValue({ ok: true, status: 204, json: async () => null } as Response);

    await clearBrochureImage('prod-1');

    const [url, init] = mockApiFetch.mock.calls[0];
    expect(String(url)).toBe(
      '/api/v1/master-data/product-attachments/brochure-images/prod-1',
    );
    expect(init).toMatchObject({ method: 'DELETE' });
  });

  it('surfaces the reason the save was refused', async () => {
    mockApiFetch.mockResolvedValue({
      ok: false,
      status: 404,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: 'That file is not attached to this product' }),
    } as unknown as Response);

    await expect(setBrochureImage('prod-1', 'att-9')).rejects.toThrow(
      'That file is not attached to this product',
    );
  });
});
