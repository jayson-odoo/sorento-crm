/**
 * AC-QTSO-CRM Phase 2 (red): "Create in AutoCount" on the AutoCount worksheet.
 *
 * UAC U2, U3, U5, U18, ruling R2. The button renders ONLY when all of these hold:
 *   - app-config `project_autocount_write_enabled` is true (the admin switch, R1),
 *   - the user holds `projects.autocount.write`,
 *   - the server says the worksheet `can_export`,
 *   - the order has no `autocount_doc_no` yet.
 * "Download CSV" stays in every case (R2: the fallback when AutoCount refuses).
 * Switch off or no permission: the button is not rendered at all (not greyed).
 *
 * The test pins the wire, not the module names: it intercepts `apiFetch` and answers
 * `/settings/app-config`, the capability read and the write route by URL.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SalesOrderWorksheet } from '../../../../../_shared/types/projectSalesOrder.types';

const apiFetch = vi.fn();
let permissions = new Set<string>();
let switchOn = true;

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, apiFetch: (...args: unknown[]) => apiFetch(...args) };
});

vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissions: [...permissions], permissionSet: permissions }),
  useHasPermission: (slug: string) => permissions.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((slug) => permissions.has(slug)),
}));

vi.mock('../../../../../_shared/services/fileDownload', () => ({
  saveBlobAs: vi.fn(),
  filenameFromContentDisposition: vi.fn(() => null),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const getSalesOrderWorksheet = vi.fn();
vi.mock('../../../../../_shared/services/projectSalesOrderService', () => ({
  PROJECT_SO_MOCK: false,
  getSalesOrderWorksheet: (...args: unknown[]) => getSalesOrderWorksheet(...args),
  downloadSalesOrderImportFile: vi.fn(),
  listProjectSalesOrders: vi.fn(),
  buildSalesOrders: vi.fn(),
  getProjectSalesOrder: vi.fn(),
  acknowledgeFinding: vi.fn(),
  updateSalesOrderLine: vi.fn(),
  regroupSalesOrder: vi.fn(),
  publishSalesOrder: vi.fn(),
  previewAmendment: vi.fn(),
  createAmendment: vi.fn(),
  getAmendment: vi.fn(),
  publishAmendment: vi.fn(),
  listScheduleVersions: vi.fn(async () => []),
  listPoVersions: vi.fn(async () => []),
}));

import { SalesOrderWorksheetClient } from './SalesOrderWorksheetClient';

const WRITE = 'projects.autocount.write';

const DONE_RESULT = {
  outcome: 'done',
  message: 'SO412345 created in AutoCount',
  doc_no: 'SO412345',
  lines: [
    {
      line_no: 1,
      item_code: 'CB6633',
      description: 'CABANA S/STEEL FLOOR GRATING 6"',
      qty: '600',
      unit_price: '11.16',
      location: 'BRW-BB',
      delivery_date: '2026-07-01',
    },
  ],
  warnings: [],
  skipped: [],
  exploded: [],
  waiting: [],
};

function json(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body, headers: new Headers() } as Response;
}

function capabilityFeed() {
  const open = { enabled: true, reason: null };
  const waiting = { enabled: false, reason: 'Waiting for AutoCount' };
  const ops = {
    create_doc: open,
    edit_doc: open,
    add_line: open,
    delete_line: waiting,
    cancel_doc: waiting,
  };
  return { enabled: switchOn, sales_orders: ops, quotations: ops };
}

function worksheet(overrides: Partial<SalesOrderWorksheet> = {}): SalesOrderWorksheet {
  return {
    id: 'so-1',
    provisional_ref: 'PSO-000101',
    autocount_doc_no: null,
    status: 'published',
    area_group: 'TOWER',
    po_number: 'HQ/26/01/121',
    customer_name: 'Hong Bee Hardware Sdn Bhd',
    header: {
      debtor: 'Hong Bee Hardware Sdn Bhd',
      your_ref_no: 'HQ/26/01/121',
      our_ref_no: 'Tuju Residences',
      our_qt_ref_no: 'QT-004188 v1',
      terms: '*Net 60 days',
    },
    lines: [
      {
        line_no: 1,
        item_code: 'CB6633',
        description: 'CABANA S/STEEL FLOOR GRATING 6"',
        reserve_qty: '0',
        qty: '600',
        delivery_date: '2026-07-01',
        uom: 'UNIT',
        unit_price: '11.16000',
        discount: '',
        total: '6696.00',
      },
    ],
    total_amount: '6696.00',
    findings: [],
    can_export: true,
    import_file_url: '/api/v1/project-sales/sales-orders/so-1/import-file',
    ...overrides,
  };
}

function appConfigReads() {
  return apiFetch.mock.calls.filter(([url]) => String(url).includes('settings/app-config')).length;
}

async function renderWorksheet(ws: SalesOrderWorksheet = worksheet()) {
  getSalesOrderWorksheet.mockResolvedValue(ws);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <SalesOrderWorksheetClient projectId="p1" psoId="so-1" />
    </QueryClientProvider>,
  );
  // The worksheet is on screen once its CSV button is.
  await screen.findByRole('button', { name: /Download CSV/ });
}

/** Wait until the app-config answer has been asked for AND applied, so "absent" means absent. */
async function settled() {
  await waitFor(() => expect(appConfigReads()).toBeGreaterThan(0));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  permissions = new Set([WRITE]);
  switchOn = true;
  apiFetch.mockImplementation(async (url: string) => {
    const path = String(url);
    if (path.includes('settings/app-config')) {
      return json({ project_autocount_write_enabled: switchOn });
    }
    if (path.includes('autocount-write/capabilities')) return json(capabilityFeed());
    if (path.endsWith('/sales-orders/so-1/autocount')) return json(DONE_RESULT);
    return json({});
  });
});

describe('Create in AutoCount on the worksheet', () => {
  it('shows beside Download CSV when the switch is on, the permission is held, it can export and the order is not in AutoCount', async () => {
    await renderWorksheet();

    expect(await screen.findByRole('button', { name: /Create in AutoCount/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: /Download CSV/ })).toBeEnabled();
  });

  it('is not rendered at all when the switch is off, and Download CSV stays', async () => {
    switchOn = false;
    await renderWorksheet();
    await settled();

    expect(screen.queryByRole('button', { name: /Create in AutoCount/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Create in AutoCount/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Download CSV/ })).toBeEnabled();
  });

  it('is not rendered without projects.autocount.write, even with the switch on', async () => {
    permissions = new Set();
    await renderWorksheet();
    await settled();

    expect(screen.queryByRole('button', { name: /Create in AutoCount/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Download CSV/ })).toBeEnabled();
  });

  it('is not rendered when the server says the worksheet cannot export', async () => {
    await renderWorksheet(worksheet({ can_export: false }));
    await settled();

    expect(screen.queryByRole('button', { name: /Create in AutoCount/ })).not.toBeInTheDocument();
  });

  it('is not rendered on a draft', async () => {
    await renderWorksheet(worksheet({ status: 'draft', can_export: false, import_file_url: null }));
    await settled();

    expect(screen.queryByRole('button', { name: /Create in AutoCount/ })).not.toBeInTheDocument();
  });

  it('is not rendered once the order is in AutoCount, and the number shows instead', async () => {
    await renderWorksheet(worksheet({ autocount_doc_no: 'SO376200' }));
    await settled();

    expect(screen.queryByRole('button', { name: /Create in AutoCount/ })).not.toBeInTheDocument();
    expect(screen.getByText('SO376200')).toBeInTheDocument();
  });

  it('presses through the write route and shows AutoCount\'s answer in the dialog', async () => {
    await renderWorksheet();

    fireEvent.click(await screen.findByRole('button', { name: /Create in AutoCount/ }));

    expect(await screen.findByText('SO412345 created in AutoCount')).toBeInTheDocument();
    const write = apiFetch.mock.calls.find(([url]) =>
      String(url).endsWith('/sales-orders/so-1/autocount'),
    );
    expect(write).toBeDefined();
    expect(write![1]).toEqual(expect.objectContaining({ method: 'POST' }));
    // The read-back line AutoCount holds is listed.
    expect(document.body.textContent).toContain('CB6633');
  });

  it('never sends a company code or a document key from the browser', async () => {
    await renderWorksheet();

    fireEvent.click(await screen.findByRole('button', { name: /Create in AutoCount/ }));
    await screen.findByText('SO412345 created in AutoCount');

    const write = apiFetch.mock.calls.find(([url]) =>
      String(url).endsWith('/sales-orders/so-1/autocount'),
    );
    const body = String((write![1] as { body?: unknown })?.body ?? '');
    expect(body).not.toMatch(/companyCode|docKey|company_id/);
  });
});
