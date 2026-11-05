/**
 * AC-QTSO-CRM Phase 2 (red): "Update in AutoCount (N)" in the amendment's AutoCount change list.
 *
 * UAC U2, U10, U11, U18, ruling R3. The button shows only when the switch is on, the user holds
 * `projects.autocount.write`, the amendment is `published` and its order is `in_autocount` (the
 * SO detail's new field). N counts only the rows the CRM can send: QTY_CHANGE, ADVANCE, DELAY and
 * ADD_LINE (REMOVE_LINE, CANCEL_BALANCE and the rest wait for AutoCount).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn();
let permissions = new Set<string>();
let switchOn = true;

const getProjectSalesOrder = vi.fn();
const previewAmendment = vi.fn();
const createAmendment = vi.fn();
const getAmendment = vi.fn();
const getAmendmentAutocountChangeList = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/sales-orders/so-1/revisions',
  useSearchParams: () => new URLSearchParams(),
}));

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

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('../../../../../_shared/services/projectSalesOrderService', () => ({
  PROJECT_SO_MOCK: false,
  listProjectSalesOrders: vi.fn(),
  buildSalesOrders: vi.fn(),
  getProjectSalesOrder: (...args: unknown[]) => getProjectSalesOrder(...args),
  acknowledgeFinding: vi.fn(),
  updateSalesOrderLine: vi.fn(),
  regroupSalesOrder: vi.fn(),
  publishSalesOrder: vi.fn(),
  previewAmendment: (...args: unknown[]) => previewAmendment(...args),
  createAmendment: (...args: unknown[]) => createAmendment(...args),
  getAmendment: (...args: unknown[]) => getAmendment(...args),
  publishAmendment: vi.fn(),
  updateAmendmentRowDecisions: vi.fn(),
  getAmendmentAutocountChangeList: (...args: unknown[]) => getAmendmentAutocountChangeList(...args),
  downloadAmendmentAutocountChangeListXlsx: vi.fn(),
  listScheduleVersions: vi.fn(async () => [
    { id: 'sched-v1', version_no: 1, revision_label: 'R1', issuer_party_label: 'Buimaco' },
    { id: 'sched-v2', version_no: 2, revision_label: 'REVISED 1', issuer_party_label: 'SLG' },
  ]),
  listPoVersions: vi.fn(async () => [{ id: 'po-v1', version_no: 1, po_number: 'HQ/26/01/121' }]),
}));

vi.mock('../../../../../_shared/hooks/useProjects', () => ({
  useProject: () => ({ data: { id: 'p1', can_edit: true }, isLoading: false, isError: false }),
  usePurchaseOrders: () => ({
    data: [{ id: 'po-1', po_number: 'HQ/26/01/121' }],
    isLoading: false,
    isError: false,
  }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
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

import { AmendmentReviewClient } from './AmendmentReviewClient';

const WRITE = 'projects.autocount.write';

function json(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body, headers: new Headers() } as Response;
}

function salesOrder(inAutocount: boolean) {
  return {
    id: 'so-1',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: inAutocount ? 'SO397450' : null,
    in_autocount: inAutocount,
    area_group: 'TOWER',
    status: 'published',
    grouping_origin: 'area',
    line_count: 99,
    total_amount: '1611107.81',
    hard_findings: 0,
    warn_findings: 0,
    is_pre_order: false,
    is_sponsorship: false,
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    lines: [],
    findings: [],
  };
}

const ROWS = [
  { so_number: 'SO397450', line_no: 1, item_code: 'A1', verb: 'QTY_CHANGE', old_qty: '10', new_qty: '8' },
  { so_number: 'SO397450', line_no: 2, item_code: 'A2', verb: 'DELAY', old_date: '2026-07-01', new_date: '2027-01-07' },
  { so_number: 'SO397450', line_no: 3, item_code: 'A3', verb: 'ADD_LINE', new_qty: '5' },
  { so_number: 'SO397450', line_no: 4, item_code: 'A4', verb: 'REMOVE_LINE' },
  { so_number: 'SO397450', line_no: 5, item_code: 'A5', verb: 'CANCEL_BALANCE', old_qty: '9', new_qty: '4' },
];

async function openAmendment({ status = 'published', inAutocount = true } = {}) {
  getProjectSalesOrder.mockResolvedValue(salesOrder(inAutocount));
  previewAmendment.mockResolvedValue({
    from: { kind: 'schedule_version', id: 'sched-v1', version_no: 1, label: 'R1' },
    to: { kind: 'schedule_version', id: 'sched-v2', version_no: 2, label: 'REVISED 1' },
    verb_summary: { DELAY: 1 },
    rows: [
      {
        so_line_id: 'l3',
        line_no: 3,
        product_code: 'SRTWC8613-RL',
        description: 'WC',
        verb: 'DELAY',
        field: 'delivery_date',
        from_value: '2026-07-01',
        to_value: '2027-01-07',
        qty: '135',
        phase_label_from: 'Level 2 & 7',
        phase_label_to: 'Level 2 & 7',
      },
    ],
    unmatched: [],
  });
  createAmendment.mockResolvedValue({
    amendment_id: 'am-1',
    ocn_id: 'ocn-1',
    ocn_number: 'OCN-000045',
    verb_summary: { DELAY: 1 },
  });
  getAmendment.mockResolvedValue({
    id: 'am-1',
    status,
    from: { kind: 'schedule_version', id: 'sched-v1', version_no: 1, label: 'R1' },
    to: { kind: 'schedule_version', id: 'sched-v2', version_no: 2, label: 'REVISED 1' },
    verb_summary: {},
    unmatched: [],
    rows: [],
    ocn_number: 'OCN-000045',
  });
  getAmendmentAutocountChangeList.mockResolvedValue({ rows: ROWS, declined_count: 0 });

  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <AmendmentReviewClient projectId="p1" psoId="so-1" />
    </QueryClientProvider>,
  );
  fireEvent.change(await screen.findByLabelText('Select a version'), {
    target: { value: 'schedule:sched-v2' },
  });
  fireEvent.click(screen.getByRole('button', { name: /Compare/ }));
  fireEvent.click(await screen.findByRole('button', { name: 'Create the amendment' }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText(/Reason/), {
    target: { value: 'Main contractor pushed the dates.' },
  });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Create the amendment' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Done' }));
  await screen.findByText('Change notice OCN-000045');
  // The AutoCount change list is on screen once its export button is.
  await screen.findByRole('button', { name: 'Export for AutoCount' });
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

beforeEach(() => {
  vi.clearAllMocks();
  permissions = new Set([WRITE]);
  switchOn = true;
  apiFetch.mockImplementation(async (url: string) => {
    const path = String(url);
    if (path.includes('settings/app-config')) {
      return json({ project_autocount_write_enabled: switchOn });
    }
    if (path.includes('autocount-write/capabilities')) {
      const open = { enabled: true, reason: null };
      const ops = { create_doc: open, edit_doc: open, add_line: open };
      return json({ enabled: switchOn, sales_orders: ops, quotations: ops });
    }
    return json({});
  });
});

describe('Update in AutoCount on a published amendment', () => {
  it('counts only the rows the CRM can send: QTY_CHANGE, ADVANCE, DELAY, ADD_LINE', async () => {
    await openAmendment();

    expect(await screen.findByRole('button', { name: 'Update in AutoCount (3)' })).toBeEnabled();
    // The export stays beside it.
    expect(screen.getByRole('button', { name: 'Export for AutoCount' })).toBeEnabled();
  });

  it('is not rendered when the switch is off', async () => {
    switchOn = false;
    await openAmendment();
    await settled();

    expect(screen.queryByRole('button', { name: /Update in AutoCount/ })).not.toBeInTheDocument();
  });

  it('is not rendered without projects.autocount.write', async () => {
    permissions = new Set();
    await openAmendment();
    await settled();

    expect(screen.queryByRole('button', { name: /Update in AutoCount/ })).not.toBeInTheDocument();
  });

  it('is not rendered while the amendment is not published', async () => {
    await openAmendment({ status: 'proposed' });
    await settled();

    expect(screen.queryByRole('button', { name: /Update in AutoCount/ })).not.toBeInTheDocument();
  });

  it('is not rendered when the order is not in AutoCount', async () => {
    await openAmendment({ inAutocount: false });
    await settled();

    expect(screen.queryByRole('button', { name: /Update in AutoCount/ })).not.toBeInTheDocument();
  });
});
