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

vi.mock('../lib/price-tag-request-service', () => ({
  lookupDebtors: vi.fn(),
  lookupPromotions: vi.fn(async () => []),
  lookupTagItems: vi.fn(),
  getRequest: vi.fn(),
  createRequest: vi.fn(),
  updateRequest: vi.fn(),
  deleteRequest: vi.fn(),
  submitRequest: vi.fn(),
  approveRequest: vi.fn(),
  requestChanges: vi.fn(),
}));

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

  it('Selling price is never disabled, and picking it reveals the optional Promotion picker inside Price (D-P2, AC-P8)', async () => {
    // role="radio" (the Price control is a radiogroup, not two plain
    // buttons). r8 owner ruling drops the r7 "disabled until a promotion is
    // picked" rule entirely - mode first, promotion second - so there is no
    // `aria-disabled` state to assert here at all, and the Promotion field
    // does not exist in the DOM until Selling is chosen.
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
    expect(await screen.findByLabelText('Promotion')).toBeInTheDocument();
    expect(screen.getByText('Promotion (optional)')).toBeInTheDocument();
  });

  it('choosing Selling price with a promotion posts price_mode selling', async () => {
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();
    // Selling first: the Promotion field only renders once Selling is chosen
    // (D-P2 - the picker moved inside the Price section).
    fireEvent.click(screen.getByRole('radio', { name: 'Selling price' }));
    await selectOption('Promotion', 'promo-1');

    submit();

    const payload = await lastCreatePayload();
    expect(payload.price_mode).toBe('selling');
    expect(payload.promotion_id).toBe('promo-1');
  });

  it('clearing the promotion while Selling is chosen keeps price_mode selling (D-P2 owner ruling: the r7 revert-to-List rule is dropped)', async () => {
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();
    fireEvent.click(screen.getByRole('radio', { name: 'Selling price' }));
    await selectOption('Promotion', 'promo-1');

    // Clear the promotion: the mocked select's own empty option.
    fireEvent.change(screen.getByLabelText('Promotion'), {
      target: { value: '' },
    });

    // Selling stays selected - AC-B5/AC-P8: Selling with no promotion is a
    // valid end state and submits fine.
    expect(
      screen.getByRole('radio', { name: 'Selling price' }),
    ).toHaveAttribute('aria-checked', 'true');

    submit();

    const payload = await lastCreatePayload();
    expect(payload.price_mode).toBe('selling');
    expect(payload.promotion_id).toBeNull();
  });

  it('switching back to List hides and clears the promotion (D-P2, AC-P8)', async () => {
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();
    fireEvent.click(screen.getByRole('radio', { name: 'Selling price' }));
    await selectOption('Promotion', 'promo-1');

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
