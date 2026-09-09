/**
 * S5 (AC-E1) - the call shape of `/api/v1/system/import-field-aliases`: which URL, which
 * method, and what the body carries. There is no mock store behind this service any more;
 * every function below reaches `apiFetch` and these tests pin what it is handed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  createImportFieldAlias,
  deleteImportFieldAlias,
  listImportFieldAliasFields,
  listImportFieldAliases,
} from './importFieldAliasService';

function jsonResponse(body: unknown, status = 200) {
  const headers = new Headers({ 'content-type': 'application/json' });
  return {
    ok: status < 400,
    status,
    headers,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue(jsonResponse([]));
});

describe('listImportFieldAliases - real backend contract', () => {
  it('GETs /api/v1/system/import-field-aliases?doc_type=', async () => {
    await listImportFieldAliases('proforma_invoice');

    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/system/import-field-aliases?doc_type=proforma_invoice',
    );
  });
});

describe('listImportFieldAliasFields - real backend contract', () => {
  it('GETs the /fields endpoint for the doc type', async () => {
    await listImportFieldAliasFields('packing_list');

    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/system/import-field-aliases/fields?doc_type=packing_list',
    );
  });
});

describe('createImportFieldAlias - real backend contract', () => {
  it('POSTs {doc_type, field, alias, locale}', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ field: 'cartons', label: 'Cartons', aliases: [] }));

    await createImportFieldAlias({
      doc_type: 'proforma_invoice',
      field: 'cartons',
      alias: '箱數',
    });

    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/system/import-field-aliases',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          doc_type: 'proforma_invoice',
          field: 'cartons',
          alias: '箱數',
        }),
      }),
    );
  });
});

describe('deleteImportFieldAlias - real backend contract', () => {
  it('DELETEs /api/v1/system/import-field-aliases/{id}', async () => {
    await deleteImportFieldAlias('alias-1');

    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/system/import-field-aliases/alias-1',
      expect.objectContaining({ method: 'DELETE' }),
    );
  });
});
