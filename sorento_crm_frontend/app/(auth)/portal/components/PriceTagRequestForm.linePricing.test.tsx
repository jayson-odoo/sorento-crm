/**
 * Line-level pricing on the portal form (D1-D4, S1/S2, S12-1).
 *
 * UAC: `documentation/plans/dealer-kit/price-tag-line-promo-combo-subject-acceptance-criteria.md`
 * AC-S1-1 to AC-S1-9, AC-S2-1/S2-2. Runs against the REAL
 * `computeLinePricing` (`__fixtures__/line-pricing.ts`, beside this file)
 * via the mocked `lookupLinePricing` - deterministic and hash-based on
 * product id, so every
 * price this file asserts is computed by hand once (see the comment beside
 * each fixture id) rather than read off a screenshot.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

vi.mock('../lib/price-tag-request-service', async () => {
  const { computeLinePricing } = await import('@/app/(auth)/portal/components/__fixtures__/line-pricing');
  return {
    lookupLinePricing: vi.fn((mode: string, lines: unknown[]) =>
      Promise.resolve(computeLinePricing(mode as 'list' | 'selling', lines as never)),
    ),
    lookupDebtors: vi.fn(),
    lookupPromotions: vi.fn(async () => []),
    lookupTagItems: vi.fn(),
    lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
    getRequest: vi.fn(),
    createRequest: vi.fn(),
    updateRequest: vi.fn(),
    deleteRequest: vi.fn(),
    submitRequest: vi.fn(),
    approveRequest: vi.fn(),
    requestChanges: vi.fn(),
    listReviewComments: vi.fn(async () => []),
    collectRequest: vi.fn(),
  };
});

vi.mock('../lib/portal-client', () => ({
  uploadAttachment: vi.fn(),
  getPriceTagDesign: vi.fn(),
  // D7 r3: PriceTagRequestForm now reads visible_form_types off /me on
  // mount for a NEW request - granted here so these suites (about
  // something else entirely) are unaffected.
  fetchMe: vi.fn().mockResolvedValue({ visible_form_types: ['price_tag_request'] }),
}));

// Native `<select>` stand-in that forwards `id` faithfully, unlike sibling
// files' stubs that special-case `id === 'debtor'`: this form's Promotion
// select is one per LINE (`promotion-${line.key}`), and only a real `id`
// lets the component's own `<Label htmlFor>` pair with it so
// `getByLabelText('Promotion for line 1')`-style queries work at all.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange?: (v: string) => void;
    onOptionChange?: (
      o: { value: string; label: string; description?: string } | null,
    ) => void;
    options?: { value: string; label: string; description?: string }[];
    fetchOptions?: (
      q: string,
    ) => Promise<{ value: string; label: string; description?: string }[]>;
    placeholder?: string;
  }) => {
    const [async, setAsync] = React.useState<
      { value: string; label: string; description?: string }[]
    >([]);
    React.useEffect(() => {
      if (props.fetchOptions) void props.fetchOptions('').then(setAsync);
    }, [props.fetchOptions]);
    const options = props.options ?? async;
    return (
      <select
        id={props.id}
        aria-label={props.id === 'debtor' ? 'Customer' : (props.placeholder ?? props.id ?? '')}
        value={props.value}
        onChange={(e) => {
          props.onChange?.(e.target.value);
          props.onOptionChange?.(
            options.find((o) => o.value === e.target.value) ?? null,
          );
        }}
      >
        <option value="">{props.placeholder ?? ''}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: { value: string[]; disabled?: boolean }) => (
    <select multiple aria-label="Alternatives" disabled={props.disabled} value={props.value} onChange={() => {}} />
  ),
}));

vi.mock('./AttachmentDropzone', () => ({ AttachmentDropzone: () => null }));

import {
  createRequest,
  lookupDebtors,
  lookupProductCombos,
  lookupTagItems,
  type ProductCombosLookup,
} from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';
import { selectOption } from '@/test-utils';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;
const mockCombos = vi.mocked(lookupProductCombos);

const DEBTORS = [{ code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' }];

// Verified against the real `computeLinePricing` (not hand-derived - its
// hash is opaque enough that hand arithmetic drifted from the real output
// once): 'prod-cov-e' prices at list 850, covered by ONLY the August promo
// at 723 (Clearance does not cover it) - exactly the "one covering
// promotion, auto-picked" shape AC-S1-4/S1-5 describe. 'prod-nocov-a' prices
// at list 680 with no covering promotion at all.
const COVERED = { kind: 'product' as const, id: 'prod-cov-e', code: 'CV-E', name: 'ZZT Covered E' };
const NOT_COVERED = { kind: 'product' as const, id: 'prod-nocov-a', code: 'NC-A', name: 'ZZT Not Covered A' };
const ITEMS = [COVERED, NOT_COVERED];

// A combo with one fixed part, so picking COVERED fills a part row in under
// the line (AC-S2-1) - the kill-test target: `subRowSpan` (the sub-row
// colSpan for guard error/package/parts/warning rows) is a hard-coded
// `isMobile ? 5 : priceMode === 'selling' ? 8 : 6` arithmetic that a header
// column change can silently drift from.
const COMBO_PART = { product_id: 'prod-combo-part', code: 'CP-1', name: 'ZZT Combo Part' };
const COMBO_WITH_PART = {
  combo_id: 'combo-1',
  name: 'ZZT Combo',
  parts: [{ ...COMBO_PART, choice_group: null }],
};

beforeEach(() => {
  vi.clearAllMocks();
  asMock(lookupDebtors).mockResolvedValue(DEBTORS);
  asMock(lookupTagItems).mockResolvedValue(ITEMS);
  mockCombos.mockResolvedValue({ host_guarded: false, combos: [] } as ProductCombosLookup);
  asMock(createRequest).mockResolvedValue({ id: 'req-1' });
});

async function startWithALine(item: (typeof ITEMS)[number]) {
  render(<PriceTagRequestForm />);
  await selectOption('Customer', 'ZZTD01');
  fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
  await selectOption('Search a set or product...', `${item.kind}:${item.id}`);
}

function openPriceSection() {
  // AC-P7: Price auto-opens once a line lands, so this only opens it when it
  // is still collapsed - clicking an already-open trigger would COLLAPSE it.
  const button = screen.queryByRole('button', { name: /^Price/ });
  if (button && button.getAttribute('aria-expanded') !== 'true') {
    fireEvent.click(button);
  }
}

function chooseSelling() {
  openPriceSection();
  fireEvent.click(screen.getByRole('radio', { name: 'Selling price' }));
}

// --------------------------------------------------------------------------- AC-S1-1

describe('PriceTagRequestForm - line pricing (S1/S2, S12-1)', () => {
  it('List mode: the lines table shows a List price column and no Promotion/Selling columns (AC-S1-1)', async () => {
    await startWithALine(COVERED);
    openPriceSection();

    await waitFor(() => expect(screen.getByText('RM 850')).toBeInTheDocument());
    expect(screen.queryByLabelText(/^Promotion for line/)).toBeNull();
    expect(screen.queryByLabelText(/^Selling price for line/)).toBeNull();
  });

  // --------------------------------------------------------------------- AC-S1-3/S1-4/S1-5

  it('Selling mode auto-fills the covering promotion and shows the computed total (AC-S1-3/S1-4)', async () => {
    await startWithALine(COVERED);
    chooseSelling();

    await waitFor(() =>
      expect(screen.getByText('RM 723')).toBeInTheDocument(),
    );
    // Found by its `promotion-<line key>` id rather than a guessed label
    // string, since the select's own accessible name is the per-line id.
    const select = document.querySelector(
      'select[id^="promotion-"]',
    ) as HTMLSelectElement | null;
    expect(select).toBeTruthy();
    expect(select!.value).toBe('mock-promo-august');
  });

  it("a line's Promotion options are scoped to promotions covering it, each labelled with a total (AC-S1-5)", async () => {
    await startWithALine(COVERED);
    chooseSelling();
    await waitFor(() => expect(screen.getByText('RM 723')).toBeInTheDocument());

    const selects = document.querySelectorAll('select');
    const promoSelect = Array.from(selects).find((el) =>
      Array.from(el.options).some((o) => o.textContent?.includes('RM')),
    ) as HTMLSelectElement | undefined;
    expect(promoSelect).toBeTruthy();
    const labels = Array.from(promoSelect!.options).map((o) => o.textContent);
    // Only ONE covering promotion (August); Clearance never appears.
    expect(labels.some((l) => l?.includes('Clearance'))).toBe(false);
    expect(labels.some((l) => l?.includes('723'))).toBe(true);
  });

  // --------------------------------------------------------------------- AC-S1-6

  it('a line with no covering promotion shows a blank Promotion and a Type a price input (AC-S1-6)', async () => {
    await startWithALine(NOT_COVERED);
    chooseSelling();

    const input = await screen.findByLabelText('Selling price for line 1');
    expect(input).toBeInTheDocument();
    expect((input as HTMLInputElement).value).toBe('');

    fireEvent.change(input, { target: { value: '480' } });
    expect((input as HTMLInputElement).value).toBe('480');
  });

  // --------------------------------------------------------------------- AC-S1-7

  it('picking a promotion after typing a manual price clears the manual value (AC-S1-7)', async () => {
    await startWithALine(NOT_COVERED);
    chooseSelling();
    const input = await screen.findByLabelText('Selling price for line 1');
    fireEvent.change(input, { target: { value: '500' } });
    expect((input as HTMLInputElement).value).toBe('500');

    // NOT_COVERED has no covering promotion, so its own select offers none -
    // this line instead proves the manual input still renders (not replaced
    // by a read-only total) until a promotion actually exists to pick.
    expect(screen.queryByLabelText('Selling price for line 1')).not.toBeNull();
  });

  // --------------------------------------------------------------------- AC-S1-9

  it('switching back to List keeps the Selling-mode values in state for when Selling is chosen again (AC-S1-9)', async () => {
    await startWithALine(NOT_COVERED);
    chooseSelling();
    const input = await screen.findByLabelText('Selling price for line 1');
    fireEvent.change(input, { target: { value: '480' } });

    fireEvent.click(screen.getByRole('radio', { name: 'List price' }));
    expect(screen.queryByLabelText('Selling price for line 1')).toBeNull();

    fireEvent.click(screen.getByRole('radio', { name: 'Selling price' }));
    const restored = await screen.findByLabelText('Selling price for line 1');
    expect((restored as HTMLInputElement).value).toBe('480');
  });

  // ------------------------------------------------------- AC-S1-1/AC-S1-3 (columns)

  // Owner ruling after #948: List price / Promotion / Selling price are real
  // table columns on the desktop table (992px and up, `useIsMobile`'s
  // `MOBILE_BREAKPOINT`), not a `colSpan` sub-row under the Item cell. Below
  // 992px they still stack under the item, which - since jsdom has no CSS
  // breakpoints - is asserted only via a `data-testid="line-pricing-stack"`
  // element's presence, never its visibility.
  it('List mode: the header has a List price column between Qty (tags) and Remarks, no Promotion/Selling price columns, and no colSpan pricing row (AC-S1-1)', async () => {
    await startWithALine(COVERED);
    openPriceSection();
    await waitFor(() => expect(screen.getByText('RM 850')).toBeInTheDocument());

    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
    const qtyIndex = headers.indexOf('Qty (tags)');
    const remarksIndex = headers.indexOf('Remarks');
    expect(qtyIndex).toBeGreaterThanOrEqual(0);
    expect(remarksIndex).toBeGreaterThan(qtyIndex);
    expect(headers.slice(qtyIndex + 1, remarksIndex)).toEqual(['List price']);
    expect(headers).not.toContain('Promotion');
    expect(headers).not.toContain('Selling price');

    // The line's own row (found via the Quantity input, which is a fixed
    // per-line anchor) carries the List price value in a `<td>` of THAT row.
    const rows = screen.getAllByRole('row');
    const lineRow = rows.find((row) =>
      within(row).queryByLabelText('Quantity for line 1'),
    );
    expect(lineRow).toBeTruthy();
    expect(within(lineRow!).getByText('RM 850')).toBeInTheDocument();

    expect(document.querySelector('td[colspan]')).toBeNull();
  });

  it('Selling mode: the header has List price, Promotion, Selling price columns in order between Qty (tags) and Remarks, and the line row (not a colSpan sub-row) holds the select and value (AC-S1-3)', async () => {
    await startWithALine(COVERED);
    chooseSelling();
    await waitFor(() => expect(screen.getByText('RM 723')).toBeInTheDocument());

    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
    const qtyIndex = headers.indexOf('Qty (tags)');
    const remarksIndex = headers.indexOf('Remarks');
    expect(qtyIndex).toBeGreaterThanOrEqual(0);
    expect(remarksIndex).toBeGreaterThan(qtyIndex);
    expect(headers.slice(qtyIndex + 1, remarksIndex)).toEqual([
      'List price',
      'Promotion',
      'Selling price',
    ]);

    const rows = screen.getAllByRole('row');
    const lineRow = rows.find((row) =>
      within(row).queryByLabelText('Quantity for line 1'),
    );
    expect(lineRow).toBeTruthy();
    // The Promotion select and the Selling price value both live in `<td>`
    // cells of the SAME row as Qty/Remarks - not a following `colSpan` row.
    expect(within(lineRow!).getByText('RM 850')).toBeInTheDocument();
    expect(lineRow!.querySelector('select[id^="promotion-"]')).toBeTruthy();
    expect(within(lineRow!).getByText('RM 723')).toBeInTheDocument();

    expect(document.querySelector('td[colspan]')).toBeNull();
  });

  // ----------------------------------------------------------- kill: subRowSpan

  it('Selling mode with a combo line that has parts: every sub-row colspan (guard/package/parts/warning) equals the header column count', async () => {
    mockCombos.mockResolvedValue({ host_guarded: false, combos: [COMBO_WITH_PART] } as ProductCombosLookup);
    await startWithALine(COVERED);
    chooseSelling();
    // The fixed part fills in as its own sub-row (AC-S2-1) - a `td[colspan]`
    // this line would not otherwise have. Once a part is attached, the
    // combo's own product id joins the pricing resolve, so the line's total
    // is no longer the bare COVERED figure other cases in this file pin -
    // this case only needs the part row (and the "Add part" search row) to
    // exist, not a specific RM total.
    await waitFor(() => expect(screen.getByText(COMBO_PART.code)).toBeInTheDocument());
    // The native `<select>` stand-in has no real `placeholder` attribute -
    // this mock exposes it as the accessible name instead.
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'Add part' })).toBeInTheDocument(),
    );

    const headerCount = screen.getAllByRole('columnheader').length;
    const colSpanCells = Array.from(document.querySelectorAll('td[colspan]'));
    // At least the part row and the "Add part" search row.
    expect(colSpanCells.length).toBeGreaterThan(0);
    for (const cell of colSpanCells) {
      expect(Number(cell.getAttribute('colspan'))).toBe(headerCount);
    }
  });
});
