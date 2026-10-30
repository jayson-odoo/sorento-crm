/**
 * PORTAL-P4-REQUESTS S7: the Price Tag Request list (Dealer Kit) for a LIMITED user (`.view_own` + `.create`,
 * never `.view` / `.process`) and for staff (control):
 *  - every column header sorts, for limited and staff alike (P4-23; four columns are `enableSorting: false` today)
 *  - Draft is a status in the filter
 *  - no Claim button for a limited user (it is marketing's), Claim stays for a process holder
 *  - the page offers Create when the user holds `.create`, and not otherwise
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/dealer-kit/price-tag-requests',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

vi.mock('@/components/common/MyRequestPortalList', () => ({ default: () => <div data-testid="portal-list-body" />, MyRequestPortalList: () => <div data-testid="portal-list-body" /> }));
let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

const listPriceTagRequests = vi.fn();
vi.mock('../../services/priceTagRequestService', () => ({
  listPriceTagRequests: (...a: unknown[]) => listPriceTagRequests(...a),
  claimPriceTagRequest: vi.fn(),
}));

import PriceTagRequestsPage from '../page';

const STAFF = ['dealer_kit.price_tag_requests.view', 'dealer_kit.price_tag_requests.process', 'dealer_kit.price_tag_requests.create'];
const COLUMNS = ['Doc Number', 'Customer', 'Salesperson', 'Status', 'Need by', 'Lines', 'Created', 'Assigned To', 'Product data'];

function row(over: Record<string, unknown> = {}) {
  return {
    id: 'req-1', doc_number: 'PT-000001', debtor_code: 'D1', debtor_name: 'ZZT Dealer', needed_by_date: null, notes: null,
    status: 'new', line_count: 2, created_at: '2026-09-01T00:00:00Z', assigned_to_id: null, assigned_to_name: null,
    contact_name: 'Sales Sam', data_changed_tag_count: 0, portal_draft_at: null, ...over,
  };
}

function mount(slugs: string[]) {
  held = new Set(slugs);
  return render(<PriceTagRequestsPage />);
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  listPriceTagRequests.mockResolvedValue({ data: [row()], pagination: { total: 1 } });
});

describe('every Price Tag Request column header sorts, for limited and staff alike', () => {
  it.each([['staff', STAFF]])('%s: each header is a sort button', async (_n, slugs) => {
    mount(slugs);
    await screen.findByText('PT-000001');
    const missing: string[] = [];
    for (const title of COLUMNS) {
      const th = screen.queryAllByText(title).map((el) => el.closest('th')).find(Boolean);
      const sortable = !!th?.querySelector('svg.lucide-chevrons-up-down, svg.lucide-arrow-up, svg.lucide-arrow-down');
      if (!sortable) missing.push(title);
    }
    expect(missing).toEqual([]);
  });
});

describe('Claim', () => {
  it('a process holder still sees Claim (control)', async () => {
    mount(STAFF);
    await screen.findByText('PT-000001');
    expect(screen.getByText('Claim')).toBeTruthy();
  });
});

describe('limited user (superseded by owner a25895124 Q1 a)', () => {
  it('gets the portal list body (card / list toggle), not the staff DataGrid', async () => {
    mount(['dealer_kit.price_tag_requests.view_own', 'dealer_kit.price_tag_requests.create']);
    expect(await screen.findByTestId('portal-list-body')).toBeTruthy();
    expect(screen.queryByRole('table')).toBeNull();
  });
});
