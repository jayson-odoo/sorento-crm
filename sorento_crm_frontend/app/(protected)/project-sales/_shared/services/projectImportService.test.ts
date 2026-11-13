/**
 * PROJECT-MIGRATION-TOOL slice 2 (RED, written before the service exists).
 *
 * Contract: PLAN-project-import-12nov.md "Frontend contract", routes as built in
 * sorento_crm_backend/app/api/v1/projects/project_import.py.
 *
 * Assumed exports of `./projectImportService` (the coder matches these):
 *   listRuns(grid: DataGridParamsInput, filters?: { status?: string[]; uploaded_by?: string[] })
 *   getRun(runId)
 *   createRun(file: File)                                   POST multipart `file`
 *   saveColumns(runId, { sheets, columns })                 PUT  /columns
 *   listLines(runId, kind, grid, filters?: { status?: 'todo' | 'set' })
 *   getLinesSummary(runId)                                  GET  /lines/summary
 *   setLine(runId, body)                                    PUT  /lines
 *   bulkSetLines(runId, body)                               PUT  /lines/bulk
 *   previewRun(runId)                                       POST /preview
 *   listRows(runId, grid, filters?: { outcome?: string[]; code?: string[]; sheet?: string[] })
 *   startImport(runId)                                      POST /import -> { job_id }
 * Every list builds its query with `buildDataGridParams` (multi filters as repeated params)
 * and every failure surfaces `extractApiError`'s message.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import {
  bulkSetLines,
  createRun,
  getLinesSummary,
  getRun,
  listLines,
  listRows,
  listRuns,
  previewRun,
  saveColumns,
  setLine,
  startImport,
} from './projectImportService';

const mockedFetch = vi.mocked(apiFetch);
const BASE = '/api/v1/projects/import';
const RUN = 'run-1';
const grid = {
  pageIndex: 1,
  pageSize: 25,
  sorting: [{ id: 'run_no', desc: true }],
  searchQuery: 'pim',
};

function okResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response;
}

function failing(detail: string): Response {
  return {
    ok: false,
    status: 422,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail }),
    text: async () => '',
    clone() {
      return this;
    },
  } as unknown as Response;
}

function call(i = 0): { url: URL; init: RequestInit } {
  const [raw, init] = mockedFetch.mock.calls[i];
  return { url: new URL(raw as string, 'http://localhost'), init: (init ?? {}) as RequestInit };
}

function method(init: RequestInit): string {
  return (init.method ?? 'GET').toUpperCase();
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedFetch.mockResolvedValue(okResponse({ data: [], items: [], total: 0 }));
});

describe('listRuns', () => {
  it('GETs /runs with the DataGrid params and the multi filters as repeated params', async () => {
    await listRuns(grid, { status: ['draft', 'imported'], uploaded_by: ['u1', 'u2'] });

    const { url, init } = call();
    expect(method(init)).toBe('GET');
    expect(url.pathname).toBe(`${BASE}/runs`);
    expect(url.searchParams.get('page')).toBe('2');
    expect(url.searchParams.get('limit')).toBe('25');
    expect(url.searchParams.get('sort')).toBe('run_no');
    expect(url.searchParams.get('dir')).toBe('desc');
    expect(url.searchParams.get('query')).toBe('pim');
    expect(url.searchParams.getAll('status')).toEqual(['draft', 'imported']);
    expect(url.searchParams.getAll('uploaded_by')).toEqual(['u1', 'u2']);
  });

  it('sends no filter param when none is ticked', async () => {
    await listRuns({ pageIndex: 0, pageSize: 25 });

    const { url } = call();
    expect(url.searchParams.get('status')).toBeNull();
    expect(url.searchParams.get('uploaded_by')).toBeNull();
    expect(url.searchParams.get('page')).toBe('1');
  });

  it('surfaces the server message on failure', async () => {
    mockedFetch.mockResolvedValue(failing('Runs are unavailable'));
    await expect(listRuns(grid)).rejects.toThrow('Runs are unavailable');
  });
});

describe('run routes', () => {
  it('getRun GETs /runs/{id}', async () => {
    mockedFetch.mockResolvedValue(okResponse({ id: RUN, run_no: 'PIM-0001' }));
    const run = await getRun(RUN);
    const { url, init } = call();
    expect(method(init)).toBe('GET');
    expect(url.pathname).toBe(`${BASE}/runs/${RUN}`);
    expect(run).toMatchObject({ run_no: 'PIM-0001' });
  });

  it('createRun POSTs the file as multipart field "file"', async () => {
    const file = new File([new Uint8Array([80, 75])], 'SO SUMMARY.xlsx');
    await createRun(file);
    const { url, init } = call();
    expect(method(init)).toBe('POST');
    expect(url.pathname).toBe(`${BASE}/runs`);
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get('file')).toBeInstanceOf(File);
  });

  it('createRun surfaces a 422 message (bad upload)', async () => {
    mockedFetch.mockResolvedValue(failing('This file is not an Excel workbook.'));
    await expect(createRun(new File(['x'], 'notes.txt'))).rejects.toThrow(
      'This file is not an Excel workbook.'
    );
  });

  it('saveColumns PUTs {sheets, columns}', async () => {
    await saveColumns(RUN, { sheets: ["JAN'26"], columns: { customer: 'CUSTOMER ' } });
    const { url, init } = call();
    expect(method(init)).toBe('PUT');
    expect(url.pathname).toBe(`${BASE}/runs/${RUN}/columns`);
    expect(JSON.parse(init.body as string)).toEqual({
      sheets: ["JAN'26"],
      columns: { customer: 'CUSTOMER ' },
    });
  });

  it('previewRun POSTs /preview', async () => {
    await previewRun(RUN);
    const { url, init } = call();
    expect(method(init)).toBe('POST');
    expect(url.pathname).toBe(`${BASE}/runs/${RUN}/preview`);
  });

  it('previewRun surfaces the refusal that names the missing field', async () => {
    mockedFetch.mockResolvedValue(failing('Choose a column for Customer.'));
    await expect(previewRun(RUN)).rejects.toThrow('Choose a column for Customer.');
  });

  it('startImport POSTs /import and returns the job id', async () => {
    mockedFetch.mockResolvedValue(okResponse({ job_id: 'job-9' }));
    const out = await startImport(RUN);
    const { url, init } = call();
    expect(method(init)).toBe('POST');
    expect(url.pathname).toBe(`${BASE}/runs/${RUN}/import`);
    expect(out).toMatchObject({ job_id: 'job-9' });
  });
});

describe('lines', () => {
  it('listLines GETs /lines with kind, status and the DataGrid params', async () => {
    await listLines(
      RUN,
      'project',
      { pageIndex: 0, pageSize: 50, sorting: [{ id: 'rows', desc: false }], searchQuery: 'tower' },
      { status: 'todo' }
    );
    const { url, init } = call();
    expect(method(init)).toBe('GET');
    expect(url.pathname).toBe(`${BASE}/runs/${RUN}/lines`);
    expect(url.searchParams.get('kind')).toBe('project');
    expect(url.searchParams.get('status')).toBe('todo');
    expect(url.searchParams.get('page')).toBe('1');
    expect(url.searchParams.get('limit')).toBe('50');
    expect(url.searchParams.get('sort')).toBe('rows');
    expect(url.searchParams.get('dir')).toBe('asc');
    expect(url.searchParams.get('query')).toBe('tower');
  });

  it('getLinesSummary GETs /lines/summary', async () => {
    mockedFetch.mockResolvedValue(okResponse({ customer: { total: 3, todo: 1 } }));
    const out = await getLinesSummary(RUN);
    const { url, init } = call();
    expect(method(init)).toBe('GET');
    expect(url.pathname).toBe(`${BASE}/runs/${RUN}/lines/summary`);
    expect(out).toMatchObject({ customer: { total: 3, todo: 1 } });
  });

  it('setLine PUTs one line', async () => {
    const body = {
      kind: 'customer',
      customer_value_key: '',
      value_key: 'CUSTOMER 001 SDN BHD',
      action: 'link',
      target_id: 'c-1',
      new_title: null,
    };
    await setLine(RUN, body);
    const { url, init } = call();
    expect(method(init)).toBe('PUT');
    expect(url.pathname).toBe(`${BASE}/runs/${RUN}/lines`);
    expect(JSON.parse(init.body as string)).toEqual(body);
  });

  it('bulkSetLines PUTs every key in ONE call', async () => {
    const body = {
      kind: 'customer',
      keys: [
        ['', 'CUSTOMER 001 SDN BHD'],
        ['', 'CUSTOMER 002 SDN BHD'],
      ] as [string, string][],
      action: 'skip',
      target_id: null,
      new_title: null,
    };
    await bulkSetLines(RUN, body);
    expect(mockedFetch).toHaveBeenCalledTimes(1);
    const { url, init } = call();
    expect(method(init)).toBe('PUT');
    expect(url.pathname).toBe(`${BASE}/runs/${RUN}/lines/bulk`);
    expect(JSON.parse(init.body as string)).toEqual(body);
  });

  it('bulkSetLines surfaces the message naming the bad line', async () => {
    mockedFetch.mockResolvedValue(failing('CUSTOMER 009 SDN BHD cannot be set this way.'));
    await expect(
      bulkSetLines(RUN, { kind: 'customer', keys: [['', 'X']], action: 'skip' })
    ).rejects.toThrow('CUSTOMER 009 SDN BHD cannot be set this way.');
  });
});

describe('listRows', () => {
  it('GETs /rows with the DataGrid params and outcome / code / sheet as repeated params', async () => {
    await listRows(
      RUN,
      { pageIndex: 0, pageSize: 50, sorting: [{ id: 'ps_number', desc: true }] },
      { outcome: ['needs_review', 'error'], code: ['customer_unmapped'], sheet: ["JAN'26"] }
    );
    const { url, init } = call();
    expect(method(init)).toBe('GET');
    expect(url.pathname).toBe(`${BASE}/runs/${RUN}/rows`);
    expect(url.searchParams.getAll('outcome')).toEqual(['needs_review', 'error']);
    expect(url.searchParams.getAll('code')).toEqual(['customer_unmapped']);
    expect(url.searchParams.getAll('sheet')).toEqual(["JAN'26"]);
    expect(url.searchParams.get('sort')).toBe('ps_number');
    expect(url.searchParams.get('dir')).toBe('desc');
  });

  it('surfaces the server message on failure', async () => {
    mockedFetch.mockResolvedValue(failing('Rows are unavailable'));
    await expect(listRows(RUN, { pageIndex: 0, pageSize: 50 })).rejects.toThrow(
      'Rows are unavailable'
    );
  });
});
