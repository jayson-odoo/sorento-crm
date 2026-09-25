import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { probeImportMapping } from './importMappingService';

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

beforeEach(() => apiFetch.mockReset());

describe('probeImportMapping', () => {
  it('carries header_field_choices through exactly as the API response states it (F1/R-D)', async () => {
    // The mapper's "Header fields" section (F2, PLAN-pi-header-fields-convert-fixes-24sep.md)
    // reads its field-select OPTIONS off `probe.header_field_choices` rather than a
    // hard-coded list, so those choices have to survive the trip from the backend's own
    // probe response through this service - today `probeImportMapping` builds its returned
    // `probe` object key by key and never copies `header_field_choices` across, so the
    // mapper always sees `undefined` regardless of what the API sent.
    apiFetch.mockResolvedValue(
      ok({
        header_row: 14,
        columns: [
          { position: 0, header: 'ITEM', samples: ['A1'], field: 'item_code', source: 'supplier', required: true },
        ],
        required_fields: ['item_code'],
        missing_required: [],
        fields: [{ field: 'item_code', label: 'Item code' }],
        row_count: 30,
        header_fields: [
          { row: 13, label: '柜号', sample: 'FSCU9304169', field: 'container_no', source: 'shared' },
        ],
        header_field_choices: [{ field: 'container_no', label: 'Container' }],
      }),
    );

    const result = await probeImportMapping({
      file: new File(['x'], 'dafuyuan.xlsx'),
      supplierId: 'sup-1',
      docTypes: ['proforma_invoice'],
    });

    expect(result.probe.header_field_choices).toEqual([
      { field: 'container_no', label: 'Container' },
    ]);
  });
});
