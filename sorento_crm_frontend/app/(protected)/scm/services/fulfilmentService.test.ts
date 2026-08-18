import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

const saveBlobAs = vi.fn();
vi.mock(
  '@/app/(protected)/project-sales/_shared/services/fileDownload',
  async (importOriginal) => ({
    ...(await importOriginal<
      typeof import('@/app/(protected)/project-sales/_shared/services/fileDownload')
    >()),
    saveBlobAs: (...a: unknown[]) => saveBlobAs(...a),
  }),
);

import { downloadPackingListExport } from './fulfilmentService';

function fileResponse(disposition: string | null, status = 200) {
  const headers = new Headers();
  if (disposition) headers.set('Content-Disposition', disposition);
  return {
    ok: status < 400,
    status,
    headers,
    blob: async () => new Blob(['xlsx']),
    json: async () => ({ message: 'nope' }),
    text: async () => 'nope',
  } as unknown as Response;
}

beforeEach(() => {
  apiFetch.mockReset();
  saveBlobAs.mockReset();
});

describe('downloadPackingListExport', () => {
  it('fetches the export route and saves the file under the server-named filename', async () => {
    apiFetch.mockResolvedValue(
      fileResponse('attachment; filename="MSKU1234567-packing-list.xlsx"'),
    );

    await downloadPackingListExport('ship-1', 'MSKU1234567');

    expect(String(apiFetch.mock.calls[0][0])).toBe(
      '/api/v1/scm/inbound-shipments/ship-1/packing-list/export',
    );
    expect(saveBlobAs).toHaveBeenCalledTimes(1);
    expect(saveBlobAs.mock.calls[0][1]).toBe('MSKU1234567-packing-list.xlsx');
  });

  it('reads an RFC 5987 encoded filename the way the shared helper does', async () => {
    apiFetch.mockResolvedValue(
      fileResponse("attachment; filename*=UTF-8''MSKU%20A-packing-list.xlsx"),
    );

    await downloadPackingListExport('ship-1', 'MSKU A');

    expect(saveBlobAs.mock.calls[0][1]).toBe('MSKU A-packing-list.xlsx');
  });

  it('falls back to the container name when the header is missing', async () => {
    apiFetch.mockResolvedValue(fileResponse(null));

    await downloadPackingListExport('ship-1', 'MSKU1234567');

    expect(saveBlobAs.mock.calls[0][1]).toBe('MSKU1234567-packing-list.xlsx');
  });

  it('falls back to "container" when neither the header nor a name is given', async () => {
    apiFetch.mockResolvedValue(fileResponse(null));

    await downloadPackingListExport('ship-1', null);

    expect(saveBlobAs.mock.calls[0][1]).toBe('container-packing-list.xlsx');
  });

  it('throws the extracted API error and saves nothing on a failed response', async () => {
    apiFetch.mockResolvedValue(fileResponse(null, 404));

    await expect(
      downloadPackingListExport('ship-1', 'MSKU1234567'),
    ).rejects.toThrow('nope');
    expect(saveBlobAs).not.toHaveBeenCalled();
  });
});
