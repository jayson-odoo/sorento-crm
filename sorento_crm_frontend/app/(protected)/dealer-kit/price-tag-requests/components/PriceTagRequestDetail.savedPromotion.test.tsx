/**
 * PORTAL-P4-REQUESTS R3b (PAR-3): the staff detail shows what the portal's read view shows for a line's promotion.
 * The read-only Promotion cell names the SAVED promotion (`promotion_name`, with the portal's ended marker from
 * `promotion_expired_on`, same wording as PriceTagLinesView via `promotionOptionName`) even when today's live
 * line-pricing options no longer contain it. Today it reads only the live options, so such a line shows "-".
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// `dismiss` is here even though `useDeferredAction` is mocked below: the
// pending-entity store this hook would otherwise drive calls `toast.dismiss`
// on its own follow-through timer, and a mock missing the key throws if
// anything in this file ever exercises the real hook.
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() } }));

// A staff `.view` holder without `.process`: the Lines tab is read-only, so the Promotion cell is text.
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => slug.endsWith('.view'),
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/price-tag-requests/req-1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="gear-menu">{children}</div>
  ),
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({
    children,
    onSelect,
  }: {
    children: React.ReactNode;
    onSelect?: (event: { preventDefault: () => void }) => void;
  }) => (
    <div role="menuitem" onClick={() => onSelect?.({ preventDefault: () => {} })}>
      {children}
    </div>
  ),
}));

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({
    pending: null,
    isPending: false,
    isBlocked: false,
    start: vi.fn(),
    cancel: vi.fn(),
    countdown: null,
  }),
}));

// Native `<select>` stand-in - the real SearchableSelect is a Radix popover
// jsdom cannot open, and both F4/F7 need the value/options directly queryable.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange?: (v: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      id={props.id}
      aria-label={props.id}
      value={props.value}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
      <option value="">{props.placeholder ?? ''}</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const { mockLookupLinePricing } = vi.hoisted(() => ({
  mockLookupLinePricing: vi.fn(),
}));

vi.mock('../../services/priceTagRequestService', () => ({
  getPriceTagRequest: vi.fn(),
  getTagSheetDoc: vi.fn(async () => null),
  claimPriceTagRequest: vi.fn(),
  transitionPriceTagRequest: vi.fn(),
  exportTagSheet: vi.fn(),
  listPriceTagRequests: vi.fn(async () => ({
    data: [],
    pagination: { total: 0, page: 1, limit: 50 },
  })),
  getRequestDesignPayload: vi.fn(async () => null),
  lookupLinePricing: mockLookupLinePricing,
  updatePriceTagLinePrice: vi.fn(),
}));

import { getPriceTagRequest } from '../../services/priceTagRequestService';
import PriceTagRequestDetail from './PriceTagRequestDetail';

const mockGet = vi.mocked(getPriceTagRequest);

function switchTab(name: string) {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0, ctrlKey: false });
}

function renderDetail() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PriceTagRequestDetail requestId="req-1" />
    </QueryClientProvider>,
  );
}

function request(lineOver: Record<string, unknown>) {
  return {
    id: 'req-1', doc_number: 'PT-202608-0001', debtor_code: 'ZZT-D1', debtor_name: 'ZZT Dealer', promotion_id: null,
    promotion_name: null, price_mode: 'selling' as const, needed_by_date: '2026-09-05', notes: null, status: 'designing',
    line_count: 1, created_at: '2026-08-30T02:00:00Z', assigned_to_id: 'user-1', assigned_to_name: 'Marketing Mei',
    contact_name: 'Sales Sam', contact_id: 'contact-1', attachments: [],
    lines: [{
      id: 'line-1', line_type: 'product', product_id: 'prod-1', product_set_id: null, name: 'ZZT Sink', code: 'SRT-1',
      show_promo_price: true, quantity: 1, included_accessories: null, sort_order: 0, list_price: 500, sell_price: 300,
      parts: [], package_warning: null, promotion_id: 'promo-zzt', promotion_name: 'ZZT Promo', promotion_expired_on: null,
      manual_sell_price: null, sell_price_basis: 'promotion',
      tags: [{
        id: 'line-1', sort_order: 0, label: '1a', quantity: 1, choices: {}, choices_display: [], open_groups: [],
        marketing_price_override: null, marketing_override_reason: null, list_price: 500, sell_price: 300,
      }],
      ...lineOver,
    }],
  } as never;
}

const live = (options: Array<Record<string, unknown>>) => [{
  key: 'line-1', list_price: 500, promotion_options: options, auto_promotion_id: options[0]?.id ?? null,
  sell_price: 300, sell_price_basis: 'promotion', parts_at_list: [], candidates: [],
}];

beforeEach(() => {
  vi.clearAllMocks();
});

describe('staff detail, read-only Promotion cell', () => {
  it('a saved promotion missing from today\'s options still shows its name and the ended marker', async () => {
    mockGet.mockResolvedValue(request({ promotion_expired_on: '2026-01-05' }));
    mockLookupLinePricing.mockResolvedValue(live([{ id: 'promo-other', description: 'ZZT Other', sell_price: 250 }]));
    renderDetail();
    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');
    await waitFor(() => expect(mockLookupLinePricing).toHaveBeenCalled());
    expect(await screen.findByText('ZZT Promo (expired 5 Jan 2026)')).toBeInTheDocument();
  });

  it('control: a saved promotion that the live options contain shows its name as today', async () => {
    mockGet.mockResolvedValue(request({}));
    mockLookupLinePricing.mockResolvedValue(live([{ id: 'promo-zzt', description: 'ZZT Promo', sell_price: 300 }]));
    renderDetail();
    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');
    expect(await screen.findByText('ZZT Promo')).toBeInTheDocument();
  });
});
