/**
 * Header price mode + line remarks (D5, D6; PLAN-portal-price-tag-journey-r8
 * D-P2/AC-P8 for the price-mode half).
 *
 * A header-level "Price" segmented control (List price / Selling price)
 * replaces the old per-line "Promo price" switch. r8 owner ruling (D-P2)
 * retires r7's "Selling disabled until a promotion is picked" rule: Selling
 * is NEVER disabled, its optional Promotion picker lives INSIDE the Price
 * section (shown only in Selling mode), and clearing the promotion no longer
 * flips the mode back to List - only an explicit switch back to List clears
 * it. Each line still carries a free-text Remarks input. `price_mode` and
 * each line's `remarks` are asserted on the payload the form posts,
 * mirroring the existing `PriceTagRequestForm.lines.test.tsx` /
 * `.validation.test.tsx` mock shape (`../lib/price-tag-request-service`
 * mocked, `SearchableSelect` stubbed to a native `<select>`).
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
  const { computeLinePricing } = await import('@/app/(auth)/portal/components/__fixtures__/line-pricing');
  return {
  lookupLinePricing: vi.fn(async (mode: string, lines: unknown[]) =>
    computeLinePricing(mode as 'list' | 'selling', lines as never),
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

// Native `<select>` stand-in: the real component is a Radix popover whose
// options only exist while open. `id` maps to the field's accessible name the
// same way the existing sibling test files do it (decoupled from the real
// visible `<Label>` text, which is a plain association here, not a lookup).
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
    const ariaLabel =
      props.id === 'debtor'
        ? 'Customer'
        : props.id === 'promotion'
          ? 'Promotion'
          : (props.placeholder ?? '');
    return (
      <select
        aria-label={ariaLabel}
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
    <select
      multiple
      aria-label="Alternatives"
      disabled={props.disabled}
      value={props.value}
      onChange={() => {}}
    />
  ),
}));

vi.mock('./AttachmentDropzone', () => ({
  AttachmentDropzone: () => null,
}));

import {
  createRequest,
  lookupDebtors,
  lookupPromotions,
  lookupTagItems,
} from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';
import { selectOption } from '@/test-utils';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const DEBTORS = [{ code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' }];
const PROMOTIONS = [{ id: 'promo-1', name: 'ZZT August Promo' }];
const ITEMS = [
  {
    kind: 'product' as const,
    id: 'prod-uuid-1',
    code: 'CBF-1234',
    name: 'ZZT Kitchen Sink',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  asMock(lookupDebtors).mockResolvedValue(DEBTORS);
  asMock(lookupPromotions).mockResolvedValue(PROMOTIONS);
  asMock(lookupTagItems).mockResolvedValue(ITEMS);
  asMock(createRequest).mockResolvedValue({ id: 'req-1' });
});

// Need by is optional since D-P2b (AC-P8b) and is no longer part of what
// Submit needs: Customer + one line + a price mode (which the form always
// carries, defaulting to List) is the whole requirement (AC-P10). Picking
// the customer auto-opens Sales Order & Lines (AC-P3), which is where the
// Item picker and Add line button live.
async function fillMinimalRequiredFields() {
  await selectOption('Customer', 'ZZTD01');
  fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
  await selectOption('Search a set or product...', 'product:prod-uuid-1');
  await pickPrinting();
}

/**
 * r9 D7: `Printing` has no default and Submit refuses without it, so every
 * test that expects a POST has to answer it first. The control lives in
 * "Additional Information", which is collapsed until a price mode is chosen.
 */
async function pickPrinting() {
  if (!screen.queryByRole('radio', { name: 'Office prints' })) {
    fireEvent.click(
      screen.getByRole('button', { name: /Additional Information/ }),
    );
  }
  fireEvent.click(await screen.findByRole('radio', { name: 'Office prints' }));
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
}

async function lastCreatePayload() {
  await waitFor(() => expect(createRequest).toHaveBeenCalled());
  return asMock(createRequest).mock.calls.at(-1)?.[0];
}

describe('PriceTagRequestForm - price mode (D5, D-P2/AC-P8)', () => {
  it('defaults to List price on a new request', async () => {
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();

    submit();

    const payload = await lastCreatePayload();
    expect(payload.price_mode).toBe('list');
  });

  // D1 (PLAN-price-tag-line-promo-combo-subject.md, this lane, S1): the
  // header's own "Promotion" picker inside Price is RETIRED - a promotion is
  // a LINE fact now, picked per row in the lines table (AC-S1-3), never at
  // the header. The four tests this replaces asserted the r8 header picker
  // (open Selling, see "Promotion", pick/clear it, watch it disappear on
  // List); full per-line coverage (auto-fill, scoped options, manual price)
  // lives in `PriceTagRequestForm.linePricing.test.tsx` (AC-S12-1). What is
  // still this file's job: Selling stays never-disabled, and no header
  // Promotion field exists in EITHER mode.
  it('Selling price is never disabled, and the header carries no Promotion field in either mode (D1, AC-S1-3)', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    // Price is collapsed until a line lands (AC-P7); opened by hand here so
    // the mode control is on screen with nothing else filled in.
    fireEvent.click(screen.getByRole('button', { name: /^Price/ }));

    expect(screen.getByRole('radio', { name: 'Selling price' })).not.toHaveAttribute(
      'aria-disabled',
    );
    expect(screen.queryByLabelText('Promotion')).toBeNull();

    fireEvent.click(screen.getByRole('radio', { name: 'Selling price' }));

    expect(screen.getByRole('radio', { name: 'Selling price' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    // D1: no header Promotion field appears even in Selling mode - it moved
    // onto the lines table.
    expect(screen.queryByLabelText('Promotion')).toBeNull();
    expect(screen.queryByText('Promotion (optional)')).toBeNull();
  });

  it('choosing Selling price posts price_mode selling with no header promotion_id (D1)', async () => {
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();
    fireEvent.click(screen.getByRole('radio', { name: 'Selling price' }));

    submit();

    const payload = await lastCreatePayload();
    expect(payload.price_mode).toBe('selling');
    // D1: the request-level `promotion_id` is dropped from the payload
    // entirely, backfilled into lines instead (AC-S6-3).
    expect(payload.promotion_id).toBeNull();
  });

  it('switching back to List keeps posting no header promotion_id (D1)', async () => {
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();
    fireEvent.click(screen.getByRole('radio', { name: 'Selling price' }));

    fireEvent.click(screen.getByRole('radio', { name: 'List price' }));

    expect(screen.queryByLabelText('Promotion')).toBeNull();

    submit();

    const payload = await lastCreatePayload();
    expect(payload.price_mode).toBe('list');
    expect(payload.promotion_id).toBeNull();
  });

  it('has no per-line "Promo price" switch anywhere on the form (AC-S2-3)', async () => {
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();

    expect(screen.queryByText(/Promo price/i)).toBeNull();
    expect(screen.queryByLabelText(/Promo price/i)).toBeNull();
  });
});

describe('PriceTagRequestForm - line remarks (D6, AC-S2-4)', () => {
  it('each line has a Remarks input, and its value is posted on submit', async () => {
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();

    const remarks = screen.getByLabelText('Remarks for line 1');
    fireEvent.change(remarks, { target: { value: 'Face out on the top shelf' } });

    submit();

    const payload = await lastCreatePayload();
    expect(payload.lines).toHaveLength(1);
    expect(payload.lines[0].remarks).toBe('Face out on the top shelf');
  });

  it('an empty remarks field posts null, matching the nullable schema column', async () => {
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();

    submit();

    const payload = await lastCreatePayload();
    expect(payload.lines[0].remarks).toBeNull();
  });
});
