/**
 * AC-QTSO-CRM Phase 2 (red): Decide > "Cancel in AutoCount" on the sales order list.
 *
 * UAC U2, U14, U18, ruling R4. The list row and the SO detail gain `in_autocount: boolean`.
 *  - Decide (N) offers "Cancel in AutoCount" only when the switch is on and the user holds
 *    `projects.autocount.write`; otherwise the item is not in the menu at all.
 *  - Its greyed reason is the capability route's `sales_orders.cancel_doc.reason`.
 *  - Ticking an order that is not `in_autocount` greys it with "Not in AutoCount yet".
 *
 * Note for the coder: an order in AutoCount is published, and today a published row's checkbox
 * is disabled (the delete rule). The row must stay tickable for Decide.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../../_shared/types/project.types';

const apiFetch = vi.fn();
const listProjectSalesOrders = vi.fn();
let permissions = new Set<string>();
let switchOn = true;
let bookNamed: string | null = 'db3';
let cancelOn = false;

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
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

vi.mock('../../_shared/services/projectSalesOrderService', () => ({
  PROJECT_SO_MOCK: false,
  listProjectSalesOrders: (...args: unknown[]) => listProjectSalesOrders(...args),
  buildSalesOrders: vi.fn(),
  deleteProjectSalesOrder: vi.fn(),
  bulkDeleteProjectSalesOrders: vi.fn(),
  saveSalesOrderDocument: vi.fn(),
  getProjectSalesOrder: vi.fn(),
  acknowledgeFinding: vi.fn(),
  updateSalesOrderLine: vi.fn(),
  regroupSalesOrder: vi.fn(),
  publishSalesOrder: vi.fn(),
  downloadSalesOrderImportFile: vi.fn(),
  previewAmendment: vi.fn(),
  createAmendment: vi.fn(),
  getAmendment: vi.fn(),
  publishAmendment: vi.fn(),
  listScheduleVersions: vi.fn(async () => []),
  listPoVersions: vi.fn(async () => []),
}));

vi.mock('../../_shared/hooks/useProjects', () => ({
  useProject: () => ({ data: undefined, isLoading: false, isError: false }),
  usePurchaseOrders: () => ({ data: [], isLoading: false, isError: false }),
  projectKey: (projectId: string) => ['projects', 'detail', projectId],
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options,
    placeholder,
  }: {
    id?: string;
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      id={id}
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { SalesOrdersPanel } from './SalesOrdersPanel';

const WRITE = 'projects.autocount.write';
const PROJECT = { id: 'p1', project_code: 'PRJ-0001', title: 'Tuju', can_edit: true } as unknown as Project;

function json(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body, headers: new Headers() } as Response;
}

function row(overrides: Record<string, unknown> = {}) {
  return {
    id: 'so-1',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: null,
    in_autocount: false,
    area_group: 'TOWER',
    status: 'draft',
    grouping_origin: 'area',
    line_count: 99,
    total_amount: '1611107.81',
    hard_findings: 0,
    warn_findings: 0,
    is_pre_order: false,
    is_sponsorship: false,
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    created_at: '2026-04-02T02:15:00',
    ...overrides,
  };
}

const IN_AUTOCOUNT = {
  id: 'so-2',
  provisional_ref: 'PSO-000124',
  autocount_doc_no: 'SO397450',
  in_autocount: true,
  status: 'published',
};

function renderPanel(rows: Record<string, unknown>[]) {
  listProjectSalesOrders.mockResolvedValue({ data: rows, total: rows.length, page: 1, limit: 25 });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <SalesOrdersPanel project={PROJECT} />
    </QueryClientProvider>,
  );
}

function appConfigReads() {
  return apiFetch.mock.calls.filter(([url]) => String(url).includes('settings/app-config')).length;
}

async function settled() {
  await waitFor(() => expect(appConfigReads()).toBeGreaterThan(0));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}

async function tick(name: string) {
  fireEvent.click(await screen.findByRole('checkbox', { name }));
}

function openDecide() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /^Decide \(\d+\)$/ }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  permissions = new Set([WRITE]);
  switchOn = true;
  bookNamed = 'db3';
  cancelOn = false;
  apiFetch.mockImplementation(async (url: string) => {
    const path = String(url);
    if (path.includes('settings/app-config')) {
      return json({ project_autocount_write_enabled: switchOn });
    }
    if (path.includes('autocount-write/capabilities')) {
      const open = { enabled: true, reason: null };
      const waiting = { enabled: false, reason: 'Waiting for AutoCount' };
      const ops = { create_doc: open, edit_doc: open, add_line: open, delete_line: waiting, cancel_doc: cancelOn ? open : waiting };
      return json({ enabled: switchOn, sales_orders: ops, quotations: ops, sales_orders_book: bookNamed });
    }
    return json({});
  });
});

describe('Decide > Cancel in AutoCount on the sales order list', () => {
  it('lists the item greyed with the capability reason for an order in AutoCount', async () => {
    renderPanel([row(IN_AUTOCOUNT)]);
    await tick('Select SO397450');

    openDecide();

    const item = await screen.findByRole('menuitem', { name: /Cancel in AutoCount/ });
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(document.body.textContent).toContain('Waiting for AutoCount');
  });

  it('greys it with "Waiting for AutoCount" while SS names no book, even when cancel is on (R8)', async () => {
    cancelOn = true;
    bookNamed = null;
    renderPanel([row(IN_AUTOCOUNT)]);
    await tick('Select SO397450');
    await settled();

    openDecide();

    const item = await screen.findByRole('menuitem', { name: /Cancel in AutoCount/ });
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(document.body.textContent).toContain('Waiting for AutoCount');
  });

  it('lets Cancel run once SS names the book and cancel is on', async () => {
    cancelOn = true;
    renderPanel([row(IN_AUTOCOUNT)]);
    await tick('Select SO397450');
    await settled();

    openDecide();

    const item = await screen.findByRole('menuitem', { name: /Cancel in AutoCount/ });
    await waitFor(() => expect(item).not.toHaveAttribute('aria-disabled', 'true'));
  });

  it('greys it with "Already cancelled in AutoCount" for a cancelled order', async () => {
    renderPanel([row({ ...IN_AUTOCOUNT, autocount_cancelled: true })]);
    await tick('Select SO397450');

    openDecide();

    const item = await screen.findByRole('menuitem', { name: /Cancel in AutoCount/ });
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(document.body.textContent).toContain('Already cancelled in AutoCount');
  });

  it('greys it with "Waiting for AutoCount" for an adopted order while SS names no book', async () => {
    renderPanel([row({ ...IN_AUTOCOUNT, autocount_adopted: true })]);
    await tick('Select SO397450');

    openDecide();

    const item = await screen.findByRole('menuitem', { name: /Cancel in AutoCount/ });
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(document.body.textContent).toContain('Waiting for AutoCount');
  });

  it('greys it with "Not in AutoCount yet" when the ticked order is not in AutoCount', async () => {
    renderPanel([row()]);
    await tick('Select PSO-000123');

    openDecide();

    const item = await screen.findByRole('menuitem', { name: /Cancel in AutoCount/ });
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(document.body.textContent).toContain('Not in AutoCount yet');
  });

  it('has no Cancel in AutoCount item when the switch is off', async () => {
    switchOn = false;
    renderPanel([row(IN_AUTOCOUNT), row()]);
    await tick('Select PSO-000123');
    await settled();

    if (screen.queryByRole('button', { name: /^Decide \(\d+\)$/ })) openDecide();

    expect(screen.queryByText(/Cancel in AutoCount/)).not.toBeInTheDocument();
  });

  it('has no Cancel in AutoCount item without projects.autocount.write', async () => {
    permissions = new Set();
    renderPanel([row(IN_AUTOCOUNT), row()]);
    await tick('Select PSO-000123');
    await settled();

    if (screen.queryByRole('button', { name: /^Decide \(\d+\)$/ })) openDecide();

    expect(screen.queryByText(/Cancel in AutoCount/)).not.toBeInTheDocument();
  });
});
