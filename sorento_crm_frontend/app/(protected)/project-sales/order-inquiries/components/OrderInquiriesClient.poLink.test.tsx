/**
 * OI-PO-LINK (`PLAN-oi-po-link-11nov.md`, UAC AC-12, AC-14, AC-15): the Order Inquiry Actions menu
 * carries the shared PO link items and the two renames. Test-FIRST: written before any of it exists.
 * Harness mirrors `OrderInquiriesClient.bulkReserve.test.tsx`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  MOCK_WORKLIST_ROWS,
  MOCK_WORKLIST_SUMMARY,
} from '../../_shared/__mocks__/orderInquiryWorklist';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';
import type { CommitReservePayload } from '../../_shared/services/orderInquiryReserveService';

const ACK = 'projects.order_inquiries.acknowledge';
const ACTION = 'projects.order_inquiry.action';

let granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((slug) => granted.has(slug)),
  usePermissions: () => ({ permissions: [...granted], permissionSet: granted, isLoading: false }),
}));

const routerReplace = vi.fn();
let currentSearchParams = new URLSearchParams('');
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: (...args: unknown[]) => routerReplace(...args) }),
  usePathname: () => '/project-sales/order-inquiries',
  useSearchParams: () => currentSearchParams,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
const prefs = vi.hoisted(() => ({
  getUserListColumnConfig: vi.fn(),
  upsertUserListColumnConfig: vi.fn(),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: (...args: unknown[]) => prefs.getUserListColumnConfig(...args),
  upsertUserListColumnConfig: (...args: unknown[]) => prefs.upsertUserListColumnConfig(...args),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));

const listOrderInquiryWorklist = vi.fn();
const getOrderInquiryWorklistSummary = vi.fn();
vi.mock('../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    listOrderInquiryWorklist: (...args: unknown[]) => listOrderInquiryWorklist(...args),
    getOrderInquiryWorklistSummary: (...args: unknown[]) => getOrderInquiryWorklistSummary(...args),
    getUnplaceAllPreview: vi.fn(async () => ({ count: 0, product_code: null, product_name: null })),
  };
});
vi.mock('../../_shared/services/orderInquiryMatrixService', () => ({
  getOrderInquiryMatrix: vi.fn(async () => ({ data: [] })),
}));
vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  // CKS1050 has only 20 at BRW in the CRM: the pen must still offer its full 44.
  getStockDetail: vi.fn(async (productId: string) => ({
    locations: [
      {
        warehouse_id: 'wh-brw',
        location: 'BRW',
        available_qty: productId === 'prod-cks' ? '20' : '200',
      },
    ],
  })),
}));

const commitSpy = vi.fn<(id: string, payload: CommitReservePayload) => Promise<unknown[]>>();
const getSummarySpy = vi.fn();
vi.mock('../../_shared/services/orderInquiryReserveService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/orderInquiryReserveService')
  >();
  return {
    ...actual,
    commitOrderInquiryReserve: (id: string, payload: CommitReservePayload) => commitSpy(id, payload),
    getReserveStatusSummary: () => getSummarySpy(),
    previewParkedReserveNotices: vi.fn(async () => ({ emails: [], unresolved: [] })),
    previewParkedReserveRequests: vi.fn(async () => ({ emails: [], unresolved: [] })),
  };
});

vi.mock('../../../scm/reorder/components/OutstandingUploadDialog', () => ({
  OutstandingUploadDialog: () => null,
}));
vi.mock('@/components/upload-activity/useUploadActivity', () => ({
  useUploadActivity: () => ({
    sessions: [],
    badgeCount: 0,
    hasInFlight: false,
    refetch: vi.fn(),
    isLoading: false,
    dismissed: new Set<string>(),
  }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(async () => undefined),
  getCurrentPendingAction: vi.fn(async () => ({ pending: null, last_outcome: null })),
}));

// A plain <select>, so a test can reach the Reserve filter by its options whatever its
// placeholder turns out to be.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    id,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    id?: string;
  }) => (
    <select
      aria-label={id ?? placeholder ?? 'select'}
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


const LINK_PO = 'projects.stock_debt.link_po';
let poLinkSwitchOn = true;
const optionsSpy = vi.fn();
vi.mock('@/app/(protected)/project-sales/_shared/po-link/usePoLink', () => ({
  usePoLinkSwitch: () => ({ data: poLinkSwitchOn, isLoading: false }),
  usePoLinkOptions: (...args: unknown[]) => {
    optionsSpy(...args);
    return {
      data: {
        capabilities: {
          split_link: { enabled: true, reason: null },
          link_row: { enabled: false, reason: null },
          unlink_row: { enabled: false, reason: null },
          relink_row: { enabled: false, reason: null },
        },
        po_lines: [],
        so_books: {},
        lines: [],
        skipped: [],
      },
      isLoading: false,
      error: null,
    };
  },
  usePoLinkMutations: () => ({
    link: { mutateAsync: vi.fn(), isPending: false },
    unlink: { mutateAsync: vi.fn(), isPending: false },
    change: { mutateAsync: vi.fn(), isPending: false },
    relink: { mutateAsync: vi.fn(), isPending: false },
    relocate: { mutateAsync: vi.fn(), isPending: false },
    resume: { mutateAsync: vi.fn(), isPending: false },
  }),
}));

import { toast } from '@/lib/toast';
import { OrderInquiriesClient } from './OrderInquiriesClient';

function line(
  id: string,
  itemCode: string,
  so: string,
  qty: string,
  inquiryId: string,
  inquiryNo: string,
  extra: Record<string, unknown> = {},
): OrderInquiryWorklistRow {
  return {
    ...MOCK_WORKLIST_ROWS[1],
    id,
    order_inquiry_id: inquiryId,
    inquiry_no: inquiryNo,
    item_code: itemCode,
    so_number: so,
    qty,
    location: 'BRW-IB',
    product_id: `prod-${itemCode.toLowerCase().replace(/[^a-z]/g, '')}`,
    state: 'raised',
    ack_state: 'acknowledged',
    reserve_state: 'requested',
    requested_qty: qty,
    reserved_qty: '0',
    reserve_warehouse_id: 'wh-brw',
    reserve_location: 'BRW',
    ...extra,
  } as unknown as OrderInquiryWorklistRow;
}


const ROW_1 = line('row-p1', 'CB313', 'SO-P1', '88', 'oi-1', 'OI-2609-0001', { product_id: 'prod-cb' });
const ROW_2 = line('row-p2', 'CB313', 'SO-P2', '12', 'oi-2', 'OI-2609-0002', { product_id: 'prod-cb' });
const ROW_3 = line('row-p3', 'CB313', 'SO-P3', '5', 'oi-3', 'OI-2609-0003', { product_id: 'prod-cb' });
const ROWS = [ROW_1, ROW_2, ROW_3];

function envelope(rows: OrderInquiryWorklistRow[]) {
  return { data: rows, total: rows.length, page: 1, limit: 25 };
}

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiriesClient />
    </QueryClientProvider>,
  );
}

async function ready() {
  renderClient();
  await screen.findByText(ROW_1.so_number as string);
}

function tick(so: string) {
  fireEvent.click(screen.getByLabelText(`Select CB313 on ${so}`));
}

function openActionsMenu() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /^actions$/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  granted = new Set([ACTION, ACK, LINK_PO]);
  poLinkSwitchOn = true;
  currentSearchParams = new URLSearchParams('');
  prefs.getUserListColumnConfig.mockResolvedValue({ listing_key: 'k', config: null });
  prefs.upsertUserListColumnConfig.mockImplementation(async (key: string, payload: unknown) => ({
    listing_key: key,
    config: payload,
  }));
  listOrderInquiryWorklist.mockResolvedValue(envelope(ROWS));
  getOrderInquiryWorklistSummary.mockResolvedValue(MOCK_WORKLIST_SUMMARY);
});

describe('AC-12 the PO link items in the Actions menu', () => {
  it('shows Link to PO, Change PO and Unlink from PO with the ticked count when the switch is on and the grant is held', async () => {
    await ready();
    tick('SO-P1');
    tick('SO-P2');
    openActionsMenu();
    expect(await screen.findByRole('menuitem', { name: /^Link to PO\.\.\. \(\d+( of \d+)?\)$/ })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /^Change PO\.\.\. \(\d+( of \d+)?\)$/ })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /^Unlink from PO\.\.\. \(\d+( of \d+)?\)$/ })).toBeInTheDocument();
  });

  it('hides all three when the switch is off', async () => {
    poLinkSwitchOn = false;
    await ready();
    tick('SO-P1');
    openActionsMenu();
    await screen.findByRole('menuitem', { name: /Auto link all/ });
    expect(screen.queryByRole('menuitem', { name: /^Link to PO/ })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: /^Change PO/ })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: /^Unlink from PO/ })).toBeNull();
  });

  it('hides all three when the user lacks the grant', async () => {
    granted = new Set([ACTION, ACK]);
    await ready();
    tick('SO-P1');
    openActionsMenu();
    await screen.findByRole('menuitem', { name: /Auto link all/ });
    expect(screen.queryByRole('menuitem', { name: /^Link to PO/ })).toBeNull();
  });
});

describe('AC-15 the two renames', () => {
  it('reads Recheck in AutoCount and Remove link in CRM, and no longer Link selected / Unlink selected', async () => {
    await ready();
    tick('SO-P1');
    openActionsMenu();
    expect(await screen.findByRole('menuitem', { name: /^Recheck in AutoCount \(1\)$/ })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /^Remove link in CRM/ })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /^Link selected/ })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: /^Unlink selected/ })).toBeNull();
  });
});

describe('AC-12 / AC-14 picking Link to PO opens the shared dialog', () => {
  it('opens a dialog titled Link to PO and asks for the options of the ticked rows', async () => {
    await ready();
    tick('SO-P1');
    tick('SO-P2');
    openActionsMenu();
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Link to PO\.\.\./ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Link to PO')).toBeInTheDocument();
    await waitFor(() => expect(optionsSpy).toHaveBeenCalled());
    expect(optionsSpy.mock.calls[0]).toContain(true);
  });
});
