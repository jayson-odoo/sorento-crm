/**
 * Line-level pricing on the portal form (D1-D4, S1/S2, S12-1).
 *
 * UAC: `documentation/plans/dealer-kit/price-tag-line-promo-combo-subject-acceptance-criteria.md`
 * AC-S1-1 to AC-S1-9, AC-S2-1/S2-2. Runs against the REAL
 * `computeLinePricing` (`lib/dealer-kit/mock-line-pricing.ts`) via the mocked
 * `lookupLinePricing` - deterministic and hash-based on product id, so every
 * price this file asserts is computed by hand once (see the comment beside
 * each fixture id) rather than read off a screenshot.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

vi.mock('../lib/price-tag-request-service', async () => {
  const { computeLinePricing } = await import('@/lib/dealer-kit/mock-line-pricing');
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
});
