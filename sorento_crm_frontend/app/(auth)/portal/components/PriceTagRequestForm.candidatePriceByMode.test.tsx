/**
 * Candidate option price follows price mode (F1, AC-S2-1).
 *
 * UAC: `documentation/plans/dealer-kit/price-tag-line-promo-combo-subject-acceptance-criteria.md`
 * AC-S2-1: "each candidate option in the part row reads `CODE  RM x` where x
 * is that candidate's list price in List mode, or its price under the
 * line's promotion (offer, else list) in Selling mode."
 *
 * A browser walk on this lane found the candidate select showing the OFFER
 * price in BOTH modes - `candidateOptionLabel` in `PriceTagRequestForm.tsx`
 * reads `pricing.candidates[].sell_price` unconditionally, with no branch on
 * `priceMode`. `lookupLinePricing` is overridden here (not the shared
 * `computeLinePricing` fixture, whose `sell_price` happens to equal
 * `list_price` in List mode and so cannot expose this bug) with a candidate
 * whose list and offer prices are deliberately different, so the two modes
 * disagree only if the component actually reads the right field.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

vi.mock('../lib/price-tag-request-service', () => ({
  lookupLinePricing: vi.fn(),
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
}));

vi.mock('../lib/portal-client', () => ({
  uploadAttachment: vi.fn(),
  getPriceTagDesign: vi.fn(),
  // D7 r3: PriceTagRequestForm now reads visible_form_types off /me on
  // mount for a NEW request - granted here so these suites (about
  // something else entirely) are unaffected.
  fetchMe: vi.fn().mockResolvedValue({ visible_form_types: ['price_tag_request'] }),
}));

// Native `<select>` stand-in matching `PriceTagRequestForm.linePricing.test.tsx`'s:
// forwards `id` faithfully so both the per-line Promotion select and this
// combo's candidate select can be found by their accessible name/placeholder.
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
          props.onOptionChange?.(options.find((o) => o.value === e.target.value) ?? null);
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
  lookupLinePricing,
  lookupProductCombos,
  lookupTagItems,
  type ProductCombosLookup,
} from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';
import { selectOption } from '@/test-utils';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;
const mockCombos = vi.mocked(lookupProductCombos);
const mockPricing = vi.mocked(lookupLinePricing);

const DEBTORS = [{ code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' }];

const HOST = { kind: 'product' as const, id: 'prod-host-tap', code: 'SRTHOST01', name: 'ZZT Host Cabinet' };
const TAP_A = { product_id: 'prod-tap-a', code: 'SRTTAPA', name: 'ZZT Tap A' };
const TAP_B = { product_id: 'prod-tap-b', code: 'SRTTAPB', name: 'ZZT Tap B' };

const COMBO_TAP_GROUP = {
  combo_id: 'combo-tap',
  name: 'Kitchen Tap combo',
  parts: [
    { ...TAP_A, choice_group: 'Kitchen Tap' },
    { ...TAP_B, choice_group: 'Kitchen Tap' },
  ],
};

// TAP_A: list 500, offer (under the line's promotion) 350.
// TAP_B: list 600, offer 420.
// Deliberately different from each other AND from their own list price, so
// the assertion cannot pass by accident.
function fixedCandidatePricing() {
  return async (_mode: string, lines: { key: string }[]) =>
    lines.map((line) => ({
      key: line.key,
      list_price: 0,
      promotion_options: [],
      auto_promotion_id: null,
      sell_price: null,
      sell_price_basis: 'list' as const,
      parts_at_list: [],
      candidates: [
        { product_id: TAP_A.product_id, list_price: 500, sell_price: 350 },
        { product_id: TAP_B.product_id, list_price: 600, sell_price: 420 },
      ],
    }));
}

beforeEach(() => {
  vi.clearAllMocks();
  asMock(lookupDebtors).mockResolvedValue(DEBTORS);
  asMock(lookupTagItems).mockResolvedValue([HOST]);
  mockCombos.mockResolvedValue({
    host_guarded: true,
    combos: [COMBO_TAP_GROUP],
  } as ProductCombosLookup);
  asMock(createRequest).mockResolvedValue({ id: 'req-1' });
  mockPricing.mockImplementation(fixedCandidatePricing());
});

async function startWithTheHost() {
  render(<PriceTagRequestForm />);
  await selectOption('Customer', 'ZZTD01');
  fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
  await selectOption('Search a set or product...', `${HOST.kind}:${HOST.id}`);
}

function openPriceSection() {
  const button = screen.queryByRole('button', { name: /^Price/ });
  if (button && button.getAttribute('aria-expanded') !== 'true') {
    fireEvent.click(button);
  }
}

describe('PriceTagRequestForm - candidate option price follows mode (F1, AC-S2-1)', () => {
  it('List mode: the candidate select reads each candidate\'s LIST price, not its offer', async () => {
    await startWithTheHost();
    openPriceSection();

    const open = await screen.findByLabelText('Not sure, any of 2');
    await waitFor(() => {
      const labels = Array.from((open as HTMLSelectElement).options).map((o) => o.textContent);
      // List mode must show list prices (500 / 600) ...
      expect(labels.some((l) => l?.includes('SRTTAPA') && l.includes('500'))).toBe(true);
      expect(labels.some((l) => l?.includes('SRTTAPB') && l.includes('600'))).toBe(true);
      // ... and must NOT show the offer prices (350 / 420) the component
      // reads unconditionally today.
      expect(labels.some((l) => l?.includes('350'))).toBe(false);
      expect(labels.some((l) => l?.includes('420'))).toBe(false);
    });
  });
});
