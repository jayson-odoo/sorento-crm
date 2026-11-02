/**
 * CRM detail: a combo line's own sell price shows (PRICETAG-COMBO AC-2.5, AC-2.6).
 *
 * AC-2.5: an open priced group leaves the sell price blank, and the cell says `-`, not RM 0.
 * AC-2.6: on a combo line with no promotion the manual box shows the figure the tag prints.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// `dismiss` is here even though `useDeferredAction` is mocked below: the
// pending-entity store this hook would otherwise drive calls `toast.dismiss`
// on its own follow-through timer, and a mock missing the key throws if
// anything in this file ever exercises the real hook.
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() } }));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
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

import {
  getPriceTagRequest,
  updatePriceTagLinePrice,
} from '../../services/priceTagRequestService';
import PriceTagRequestDetail from './PriceTagRequestDetail';

const mockGet = vi.mocked(getPriceTagRequest);
const mockUpdateLinePrice = vi.mocked(updatePriceTagLinePrice);

function switchTab(name: string) {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0, ctrlKey: false });
}

function renderDetail(requestId = 'req-1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PriceTagRequestDetail requestId={requestId} />
    </QueryClientProvider>,
  );
}

const baseRequest = {
  id: 'req-1',
  doc_number: 'PT-202608-0001',
  debtor_code: 'ARD001',
  debtor_name: 'ARDENCY CONSTRUCTION',
  promotion_id: null,
  promotion_name: null,
  price_mode: 'selling' as const,
  needed_by_date: '2026-09-05',
  notes: null,
  status: 'designing',
  line_count: 1,
  created_at: '2026-08-30T02:00:00Z',
  assigned_to_id: 'user-1',
  assigned_to_name: 'Marketing Mei',
  contact_name: 'Sales Sam',
  contact_id: 'contact-1',
  attachments: [],
};


beforeEach(() => {
  vi.clearAllMocks();
});

function comboLine(overrides: Record<string, unknown> = {}) {
  return {
    id: 'line-1',
    line_type: 'product',
    product_id: 'prod-1',
    product_set_id: null,
    name: 'Kitchen Sink',
    code: 'SRT-1',
    show_promo_price: false,
    quantity: 1,
    included_accessories: null,
    sort_order: 0,
    list_price: 1090,
    sell_price: null,
    parts: [],
    package_warning: null,
    promotion_id: null,
    promotion_name: null,
    manual_sell_price: null,
    sell_price_basis: 'list',
    combo_id: 'combo-1',
    tags: [],
    ...overrides,
  };
}

function pricing(overrides: Record<string, unknown> = {}) {
  return {
    key: 'line-1',
    list_price: 1090,
    promotion_options: [],
    auto_promotion_id: null,
    sell_price: 1099,
    sell_price_basis: 'promotion',
    parts_at_list: [],
    candidates: [],
    ...overrides,
  };
}

describe('PriceTagRequestDetail - combo line selling price', () => {
  it('AC-2.6: the manual box shows the combo price as its placeholder', async () => {
    mockGet.mockResolvedValue({ ...baseRequest, lines: [comboLine()] } as never);
    mockLookupLinePricing.mockResolvedValue([pricing()]);
    renderDetail();
    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');
    const input = await screen.findByLabelText('Selling price for SRT-1');
    await waitFor(() => expect(input).toHaveAttribute('placeholder', 'RM 1,099'));
  });

  it('AC-2.6: a list-basis line keeps the plain placeholder', async () => {
    mockGet.mockResolvedValue({ ...baseRequest, lines: [comboLine()] } as never);
    mockLookupLinePricing.mockResolvedValue([pricing({ sell_price: 1090, sell_price_basis: 'list' })]);
    renderDetail();
    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');
    const input = await screen.findByLabelText('Selling price for SRT-1');
    await waitFor(() => expect(input).toHaveAttribute('placeholder', 'Type a price'));
  });

  it('AC-2.5: a blank sell price under a promotion reads - and not RM 0', async () => {
    mockGet.mockResolvedValue({
      ...baseRequest,
      lines: [comboLine({ promotion_id: 'promo-1', promotion_name: 'Raya' })],
    } as never);
    mockLookupLinePricing.mockResolvedValue([
      pricing({
        sell_price: null,
        promotion_options: [{ id: 'promo-1', description: 'Raya', sell_price: 900 }],
        auto_promotion_id: 'promo-1',
      }),
    ]);
    renderDetail();
    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');
    await screen.findByLabelText('promotion-line-1');
    await waitFor(() => expect(mockLookupLinePricing).toHaveBeenCalled());
    expect(screen.queryByText(/RM\s*0$/)).toBeNull();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });
});
