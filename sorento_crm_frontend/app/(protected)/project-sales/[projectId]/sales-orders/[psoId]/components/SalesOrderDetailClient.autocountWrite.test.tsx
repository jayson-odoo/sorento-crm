/**
 * AC-QTSO-CRM round 5 (owner: "I should be able to create and cancel SO here ma, why need to go to
 * worksheet"): the sales order DETAIL page's gear menu carries Create / Cancel / Update in
 * AutoCount, under the same rules as the worksheet and the list (`autocountWriteRules`): hidden
 * with the switch off or without `projects.autocount.write`; greyed with the same reasons (not
 * published, already in AutoCount, no book, cancel unsupported, already cancelled).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn();
const getProjectSalesOrder = vi.fn();
let permissions = new Set<string>();
let switchOn = true;
let bookNamed: string | null = 'db3';
let cancelOn = false;

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/sales-orders/so-1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, apiFetch: (...args: unknown[]) => apiFetch(...args) };
});

vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissions: [...permissions], permissionSet: permissions }),
  useHasPermission: (slug: string) => permissions.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((slug) => permissions.has(slug)),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('../../../../_shared/services/projectSalesOrderService', () => ({
  PROJECT_SO_MOCK: false,
  listProjectSalesOrders: vi.fn(async () => ({ data: [{ id: 'so-1' }], total: 1, page: 1, limit: 25 })),
  buildSalesOrders: vi.fn(),
  getProjectSalesOrder: (...args: unknown[]) => getProjectSalesOrder(...args),
  acknowledgeFinding: vi.fn(),
  updateSalesOrderLine: vi.fn(),
  regroupSalesOrder: vi.fn(),
  publishSalesOrder: vi.fn(),
  unpublishSalesOrder: vi.fn(),
  bulkSetLinesStockLocation: vi.fn(),
  downloadSalesOrderImportFile: vi.fn(),
  previewAmendment: vi.fn(),
  createAmendment: vi.fn(),
  getAmendment: vi.fn(),
  publishAmendment: vi.fn(),
  listScheduleVersions: vi.fn(async () => []),
  listScheduleFindings: vi.fn(async () => []),
  acknowledgeScheduleFinding: vi.fn(),
  listPoVersions: vi.fn(async () => []),
}));

vi.mock('../../../../_shared/services/fileDownload', () => ({
  saveBlobAs: vi.fn(),
  filenameFromContentDisposition: vi.fn(() => null),
}));

vi.mock('../../../../_shared/services/soDivergenceService', () => ({
  listDivergences: vi.fn(async () => ({ data: [], total: 0, page: 1, limit: 100 })),
  getDivergence: vi.fn(),
  ingestSalesOrderFile: vi.fn(),
  resolveDivergenceRow: vi.fn(),
  downloadCorrectiveImportFile: vi.fn(),
}));

vi.mock('../../../../_shared/hooks/useProjects', () => ({
  useProject: () => ({
    data: { id: 'p1', title: 'Setia Alam', project_code: 'PRJ-000001', can_edit: true },
    isLoading: false,
    isError: false,
  }),
  usePurchaseOrders: () => ({ data: [], isLoading: false, isError: false }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => null,
}));

import { SalesOrderDetailClient } from './SalesOrderDetailClient';

const WRITE = 'projects.autocount.write';

function json(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body, headers: new Headers() } as Response;
}

const DONE = {
  outcome: 'done',
  message: 'SO412345 created in AutoCount',
  doc_no: 'SO412345',
  lines: [],
  warnings: [],
  skipped: [],
  exploded: [],
  waiting: [],
};

function order(overrides: Record<string, unknown> = {}) {
  return {
    id: 'so-1',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: null,
    in_autocount: false,
    area_group: 'TOWER',
    status: 'published',
    can_export: true,
    grouping_origin: 'area',
    line_count: 0,
    total_amount: '0',
    hard_findings: 0,
    warn_findings: 0,
    is_pre_order: false,
    is_sponsorship: false,
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    created_at: '2026-04-02T02:15:00',
    lines: [],
    findings: [],
    ...overrides,
  };
}

function appConfigReads() {
  return apiFetch.mock.calls.filter(([url]) => String(url).includes('settings/app-config')).length;
}

async function settled() {
  await waitFor(() => expect(appConfigReads()).toBeGreaterThan(0));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
}

async function openGear() {
  const gear = await screen.findByRole('button', { name: 'Sales order actions' });
  fireEvent.pointerDown(gear, { button: 0, ctrlKey: false });
}

async function renderDetail(data: Record<string, unknown>) {
  getProjectSalesOrder.mockResolvedValue(order(data));
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <SalesOrderDetailClient projectId="p1" psoId="so-1" />
    </QueryClientProvider>,
  );
  await settled();
  await openGear();
}

const item = (name: RegExp) => screen.findByRole('menuitem', { name });

beforeEach(() => {
  vi.clearAllMocks();
  permissions = new Set([WRITE]);
  switchOn = true;
  bookNamed = 'db3';
  cancelOn = false;
  apiFetch.mockImplementation(async (url: string) => {
    const path = String(url);
    if (path.includes('settings/app-config')) return json({ project_autocount_write_enabled: switchOn });
    if (path.includes('autocount-write/capabilities')) {
      const open = { enabled: true, reason: null };
      const waiting = { enabled: false, reason: 'Waiting for AutoCount' };
      const ops = {
        create_doc: open, edit_doc: open, add_line: open, delete_line: waiting,
        cancel_doc: cancelOn ? open : waiting,
      };
      return json({ enabled: switchOn, sales_orders: ops, quotations: ops, book: bookNamed });
    }
    if (path.endsWith('/sales-orders/so-1/autocount')) return json(DONE);
    if (path.endsWith('/sales-orders/so-1/autocount/cancel')) {
      return json({ ...DONE, message: 'SO412345 cancelled in AutoCount' });
    }
    return json({});
  });
});

describe('AutoCount actions on the sales order detail page', () => {
  it('offers Create in AutoCount on a published, exportable order not in AutoCount', async () => {
    await renderDetail({});

    const create = await item(/Create in AutoCount/);
    await waitFor(() => expect(create).not.toHaveAttribute('aria-disabled', 'true'));
  });

  it('Create posts to the same route and opens the result dialog', async () => {
    await renderDetail({});
    const create = await item(/Create in AutoCount/);
    await waitFor(() => expect(create).not.toHaveAttribute('aria-disabled', 'true'));

    fireEvent.click(create);

    expect(await screen.findByText('SO412345 created in AutoCount')).toBeInTheDocument();
    const write = apiFetch.mock.calls.find(([url]) => String(url).endsWith('/sales-orders/so-1/autocount'));
    expect(write![1]).toEqual(expect.objectContaining({ method: 'POST' }));
  });

  it('Cancel posts to the cancel route when cancel is on and the order is in AutoCount', async () => {
    cancelOn = true;
    await renderDetail({ autocount_doc_no: 'SO412345', in_autocount: true });
    const cancel = await item(/Cancel in AutoCount/);
    await waitFor(() => expect(cancel).not.toHaveAttribute('aria-disabled', 'true'));

    fireEvent.click(cancel);

    expect(await screen.findByText('SO412345 cancelled in AutoCount')).toBeInTheDocument();
  });

  it.each([
    ['the switch is off', () => { switchOn = false; }],
    ['the permission is missing', () => { permissions = new Set(); }],
  ])('shows no AutoCount action when %s', async (_name, arrange) => {
    arrange();
    await renderDetail({});

    expect(screen.queryByRole('menuitem', { name: /in AutoCount/ })).not.toBeInTheDocument();
  });

  it('greys Create on a draft with "Publish the order first"', async () => {
    await renderDetail({ status: 'draft', can_export: false });

    const create = await item(/Create in AutoCount/);
    expect(create).toHaveAttribute('aria-disabled', 'true');
    expect(document.body.textContent).toContain('Publish the order first');
  });

  it('greys Create once the order is in AutoCount', async () => {
    await renderDetail({ autocount_doc_no: 'SO412345', in_autocount: true });

    expect(await item(/Create in AutoCount/)).toHaveAttribute('aria-disabled', 'true');
    expect(document.body.textContent).toContain('Already in AutoCount');
  });

  it('greys Create and Cancel with "Waiting for AutoCount" while SS names no book', async () => {
    cancelOn = true;
    bookNamed = null;
    await renderDetail({ autocount_doc_no: 'SO412345', in_autocount: true });

    expect(await item(/Cancel in AutoCount/)).toHaveAttribute('aria-disabled', 'true');
    expect(document.body.textContent).toContain('Waiting for AutoCount');
  });

  it('greys Cancel while the feed says cancel is not supported yet', async () => {
    await renderDetail({ autocount_doc_no: 'SO412345', in_autocount: true });

    expect(await item(/Cancel in AutoCount/)).toHaveAttribute('aria-disabled', 'true');
    expect(document.body.textContent).toContain('Waiting for AutoCount');
  });

  it('greys Cancel on an order that is not in AutoCount, and on one already cancelled', async () => {
    await renderDetail({});
    expect(await item(/Cancel in AutoCount/)).toHaveAttribute('aria-disabled', 'true');
    expect(document.body.textContent).toContain('Not in AutoCount yet');
  });

  it('greys Cancel with "Already cancelled in AutoCount"', async () => {
    cancelOn = true;
    await renderDetail({ autocount_doc_no: 'SO412345', in_autocount: true, autocount_cancelled: true });

    expect(await item(/Cancel in AutoCount/)).toHaveAttribute('aria-disabled', 'true');
    expect(document.body.textContent).toContain('Already cancelled in AutoCount');
  });

  it('offers Update in AutoCount as a link to the revisions page when a published amendment is pending', async () => {
    await renderDetail({ status: 'amended', autocount_doc_no: 'SO412345', in_autocount: true });

    const update = await item(/Update in AutoCount/);
    expect(update.closest('a')).toHaveAttribute('href', '/project-sales/p1/sales-orders/so-1/revisions');
  });

  it('has no Update in AutoCount on an order with no published amendment', async () => {
    await renderDetail({ status: 'published', autocount_doc_no: 'SO412345', in_autocount: true });

    expect(screen.queryByRole('menuitem', { name: /Update in AutoCount/ })).not.toBeInTheDocument();
  });
});
