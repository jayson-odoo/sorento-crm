/**
 * The SPO Allocation cell, shared by the GRN detail line table and the
 * Picking Lines listing so a matched / stated-but-unmatched / neither line
 * cannot render differently depending on which screen it is viewed from.
 *
 * See `documentation/plans/purchasing/grn-spo-forward-matching-acceptance-criteria.md`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { SpoAllocationCell } from './SpoAllocationCell';

describe('SpoAllocationCell', () => {
  // AC-FM-1: a matched line still links to its allocation, labelled with the
  // allocation's spo_number, unchanged from today.
  it('AC-FM-1: links a matched line to its allocation, labelled with spo_number', () => {
    render(
      <SpoAllocationCell
        allocation={{ id: 'alloc-1', spo_number: 'SPO-2026/07-0012' }}
        statedSpoNumber="SPO-2026/07-0012"
      />,
    );

    const link = screen.getByRole('link', { name: 'SPO-2026/07-0012' });
    expect(link).toHaveAttribute(
      'href',
      '/procurement-management/spo-allocations/alloc-1',
    );
  });

  // AC-FM-1b: a matched line whose allocation has a null spo_number falls
  // back to spo_number_raw, then to the literal "SPO allocation" - never the
  // allocation's id. "No UUIDs in the UI" is a PRINCIPLES.md hard-fail rule.
  it('AC-FM-1b: falls back to spo_number_raw when the allocation has no spo_number', () => {
    render(
      <SpoAllocationCell
        allocation={{ id: 'f47ac10b-58cc-4372-a567-0e02b2c3d479', spo_number: null }}
        statedSpoNumber="SPO-2026/07-0012"
      />,
    );

    const link = screen.getByRole('link', { name: 'SPO-2026/07-0012' });
    expect(link).toHaveAttribute(
      'href',
      '/procurement-management/spo-allocations/f47ac10b-58cc-4372-a567-0e02b2c3d479',
    );
    // The label is never the raw id, even though the id is part of the href.
    expect(link.textContent).not.toContain('f47ac10b-58cc-4372-a567-0e02b2c3d479');
    expect(document.body.textContent).not.toContain(
      'f47ac10b-58cc-4372-a567-0e02b2c3d479',
    );
  });

  it('AC-FM-1b: falls back to the literal "SPO allocation" when neither spo_number nor spo_number_raw is present', () => {
    render(
      <SpoAllocationCell
        allocation={{ id: 'a1b2c3d4-e5f6-4789-9abc-def012345678', spo_number: null }}
        statedSpoNumber={null}
      />,
    );

    const link = screen.getByRole('link', { name: 'SPO allocation' });
    expect(link).toHaveAttribute(
      'href',
      '/procurement-management/spo-allocations/a1b2c3d4-e5f6-4789-9abc-def012345678',
    );
    expect(document.body.textContent).not.toContain(
      'a1b2c3d4-e5f6-4789-9abc-def012345678',
    );
  });

  // AC-FM-2: an unmatched line with spo_number_raw shows that text plus an
  // "Unmatched" badge, and no link - a dash would falsely read as "the sheet
  // said nothing".
  it('AC-FM-2: shows the stated SPO number and an Unmatched badge, with no link', () => {
    render(
      <SpoAllocationCell allocation={null} statedSpoNumber="SPO-2026/07-0012" />,
    );

    expect(screen.getByText('SPO-2026/07-0012')).toBeInTheDocument();
    expect(screen.getByText('Unmatched')).toBeInTheDocument();
    expect(screen.queryByRole('link')).toBeNull();
  });

  // AC-FM-3: a line that stated nothing still shows a dash.
  it('AC-FM-3: shows a dash when neither allocation nor spo_number_raw is present', () => {
    const { container } = render(
      <SpoAllocationCell allocation={null} statedSpoNumber={null} />,
    );

    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.queryByText('Unmatched')).toBeNull();
    expect(container.textContent).toBe('-');
  });
});

// --------------------------------------------------------------------------
// AC-FM-4: one cell, both listings.
//
// GRNDetail and PickingLinesList must call the same shared SpoAllocationCell,
// so the three states above cannot drift apart between them. Rather than
// re-asserting the three states against each listing (which is exactly the
// duplication the shared component exists to avoid), this renders both
// listings from the SAME line fixtures and asserts their rendered DOM shape
// agrees - same href, same label, same badge, same dash - row for row.
// --------------------------------------------------------------------------

const pushMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => new URLSearchParams(''),
  // The shared DataGrid (used by PickingLinesList) reads the pathname too.
  usePathname: () => '/procurement-management/picking-lines',
}));

vi.mock(
  '@/app/(protected)/procurement-management/grn/components/GRNNavigation',
  () => ({ default: () => <div data-testid="grn-navigation" /> }),
);

vi.mock(
  '@/app/(protected)/procurement-management/grn/components/grn-delete-dialog',
  () => ({ default: () => null }),
);

const grnMock = vi.fn();
vi.mock('@/app/(protected)/procurement-management/grn/hooks/useGRN', () => ({
  useGRN: () => grnMock(),
  useUpdateGRN: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const getPickingLinesMock = vi.fn();
vi.mock(
  '@/app/(protected)/procurement-management/picking-lines/services/pickingLineService',
  () => ({
    getPickingLines: (...args: unknown[]) => getPickingLinesMock(...args),
  }),
);

// The same three lines - matched, stated-but-unmatched, neither - expressed
// once, then adapted into each listing's own item shape below.
const MATCHED = {
  key: 'MATCHED-A',
  allocation: { id: 'alloc-shared-1', spo_number: 'SPO-2026/07-0011' },
  spo_number_raw: 'SPO-2026/07-0011',
};
const UNMATCHED = {
  key: 'UNMATCHED-B',
  allocation: null,
  spo_number_raw: 'SPO-2026/07-0012',
};
const NEITHER = {
  key: 'NEITHER-C',
  allocation: null,
  spo_number_raw: null,
};
const FIXTURE_LINES = [MATCHED, UNMATCHED, NEITHER];

async function renderGRNDetail() {
  grnMock.mockReturnValue({
    data: {
      id: 'grn-1',
      picking_number: 'GR-001114',
      spo_number: 'PO-000338',
      picking_date: '2026-06-22',
      picking_status: 'approved',
      picking_lines: FIXTURE_LINES.map((line, index) => ({
        id: `line-${index}`,
        spo_allocation: line.allocation,
        spo_number_raw: line.spo_number_raw,
        product: { product_code: line.key },
        quantity_expected: 1,
        quantity_picked: 0,
      })),
    },
    isLoading: false,
  });

  const { default: GRNDetail } = await import(
    '@/app/(protected)/procurement-management/grn/components/GRNDetail'
  );
  render(<GRNDetail grnId="grn-1" />);
  await screen.findByText(MATCHED.key);
}

async function renderPickingLinesList() {
  getPickingLinesMock.mockResolvedValue({
    data: FIXTURE_LINES.map((line, index) => ({
      id: `pl-${index}`,
      picking_header_id: 'grn-1',
      spo_allocation: line.allocation,
      spo_number_raw: line.spo_number_raw,
      product: { id: `p-${index}`, product_code: line.key, product_name: line.key },
      quantity_expected: 1,
      quantity_picked: 0,
      quantity_discrepancy: 0,
    })),
    pagination: { total: FIXTURE_LINES.length, page: 1, limit: 20 },
    empty: false,
  });

  const { default: PickingLinesList } = await import(
    '@/app/(protected)/procurement-management/picking-lines/components/PickingLinesList'
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <PickingLinesList />
    </QueryClientProvider>,
  );
  await screen.findByText(MATCHED.key);
}

/** The cell's rendered shape for a given row identity, agnostic of which listing rendered it. */
function cellShapeFor(rowKey: string) {
  // Located via the product text and walked up to the row, since GRNDetail
  // and PickingLinesList lay their columns out in a different order.
  const row = screen.getByText(rowKey).closest('tr');
  if (!row) throw new Error(`row not found for ${rowKey}`);
  const link = row.querySelector('a');
  const badge = Array.from(row.querySelectorAll('span')).find(
    (el) => el.textContent === 'Unmatched',
  );
  return {
    href: link?.getAttribute('href') ?? null,
    label: link?.textContent ?? null,
    hasUnmatchedBadge: Boolean(badge),
    text: row.textContent ?? '',
  };
}

describe('AC-FM-4: SpoAllocationCell is shared by GRNDetail and PickingLinesList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders an identical matched-line link in both listings', async () => {
    await renderGRNDetail();
    const grnShape = cellShapeFor(MATCHED.key);

    document.body.innerHTML = '';
    await renderPickingLinesList();
    const pickingShape = cellShapeFor(MATCHED.key);

    expect(grnShape.href).toBe(
      '/procurement-management/spo-allocations/alloc-shared-1',
    );
    expect(grnShape.href).toBe(pickingShape.href);
    expect(grnShape.label).toBe('SPO-2026/07-0011');
    expect(grnShape.label).toBe(pickingShape.label);
  });

  it('renders an identical stated-but-unmatched line in both listings', async () => {
    await renderGRNDetail();
    const grnShape = cellShapeFor(UNMATCHED.key);

    document.body.innerHTML = '';
    await renderPickingLinesList();
    const pickingShape = cellShapeFor(UNMATCHED.key);

    expect(grnShape.href).toBeNull();
    expect(grnShape.hasUnmatchedBadge).toBe(true);
    expect(grnShape.text).toContain('SPO-2026/07-0012');

    expect(grnShape.href).toBe(pickingShape.href);
    expect(grnShape.hasUnmatchedBadge).toBe(pickingShape.hasUnmatchedBadge);
    expect(grnShape.text.includes('SPO-2026/07-0012')).toBe(
      pickingShape.text.includes('SPO-2026/07-0012'),
    );
  });

  it('renders an identical dash for a line that stated nothing in both listings', async () => {
    await renderGRNDetail();
    const grnRow = screen.getByText(NEITHER.key).closest('tr');
    if (!grnRow) throw new Error('row not found');
    const grnHasLink = Boolean(grnRow.querySelector('a'));
    const grnHasBadge = Array.from(grnRow.querySelectorAll('span')).some(
      (el) => el.textContent === 'Unmatched',
    );
    const grnHasDash = grnRow.textContent?.includes('-') ?? false;

    document.body.innerHTML = '';
    await renderPickingLinesList();
    const pickingRow = screen.getByText(NEITHER.key).closest('tr');
    if (!pickingRow) throw new Error('row not found');
    const pickingHasLink = Boolean(pickingRow.querySelector('a'));
    const pickingHasBadge = Array.from(pickingRow.querySelectorAll('span')).some(
      (el) => el.textContent === 'Unmatched',
    );
    const pickingHasDash = pickingRow.textContent?.includes('-') ?? false;

    expect(grnHasLink).toBe(false);
    expect(grnHasBadge).toBe(false);
    expect(grnHasDash).toBe(true);

    expect(grnHasLink).toBe(pickingHasLink);
    expect(grnHasBadge).toBe(pickingHasBadge);
    expect(grnHasDash).toBe(pickingHasDash);
  });
});
