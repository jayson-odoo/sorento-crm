/**
 * PRICETAG-LPSP S6: the form's header default, per-line LP/SP, the AI extract apply and two copy
 * changes. UAC: AC-19, AC-22, AC-23, AC-25.
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). Same harness as `PriceTagRequestForm.priceMode.test.tsx`
 * (service mocked, SearchableSelect stubbed to a native select), plus the AI dialog stubbed to a
 * prop-capturing component as `PriceTagRequestForm.aiExtractApply.test.tsx` does. Payload
 * assertions go through Escalate to marketing, which runs the same checks as Approve.
 *
 * Contract: each posted line carries `price_type`; a new line takes the header mode at the moment
 * it is added; the header radiogroup is named "Preferred Default" (its two radios keep
 * "List price" / "Selling price"); the apply maps `price_type`, `typed_sell_price` (as the manual
 * price, SP lines only) and `combo_id` of a matched row; an unmatched "+" row adds no line.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
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
  submitAndEscalate: vi.fn().mockResolvedValue({ status: 'new' }),
  submitAndApprove: vi.fn().mockResolvedValue({ status: 'approved' }),
  lookupTagPreviewForRequest: vi.fn(),
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

type CapturedProps = {
  onExtracted?: (products: unknown[]) => void;
  onApply?: (payload: { productLines: unknown[]; files?: File[]; alsoAttach?: boolean }) => void;
};
let captured: CapturedProps = {};
vi.mock('./AIExtractDialog', () => ({
  AIExtractDialog: (props: CapturedProps) => {
    captured = props;
    return null;
  },
}));


import {
  createRequest,
  lookupDebtors,
  lookupPromotions,
  lookupTagItems,
  lookupProductCombos,
} from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';
import { selectOption } from '@/test-utils';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const DEBTORS = [{ code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' }];
const ITEMS = [
  { kind: 'product' as const, id: 'prod-uuid-1', code: 'CBF-1234', name: 'ZZT Kitchen Sink' },
];

const P1 = { id: 'prod-uuid-1', code: 'CBF-1234', name: 'ZZT Kitchen Sink' };
const P2 = { id: 'prod-uuid-2', code: 'CBF-5678', name: 'ZZT Basin' };
const P3 = { id: 'prod-uuid-3', code: 'CBF-9999', name: 'ZZT Mirror' };
const BY_CODE: Record<string, typeof P1> = {
  [P1.code]: P1,
  [P2.code]: P2,
  [P3.code]: P3,
};

beforeEach(() => {
  vi.clearAllMocks();
  captured = {};
  asMock(lookupDebtors).mockResolvedValue(DEBTORS);
  asMock(lookupPromotions).mockResolvedValue([]);
  asMock(lookupTagItems).mockResolvedValue(ITEMS);
  asMock(createRequest).mockResolvedValue({ id: 'req-1' });
});

function sendToMarketing() {
  if (!screen.queryByLabelText('What marketing needs to fix')) {
    fireEvent.click(screen.getByRole('button', { name: /escalate to marketing/i }));
  }
  fireEvent.change(screen.getByLabelText('What marketing needs to fix'), {
    target: { value: 'Please check' },
  });
  fireEvent.click(screen.getByRole('button', { name: /send to marketing/i }));
}

async function lastCreatePayload() {
  await waitFor(() => expect(createRequest).toHaveBeenCalled());
  return asMock(createRequest).mock.calls.at(-1)?.[0];
}

async function addPickedLine() {
  fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
  await selectOption('Search a set or product...', 'product:prod-uuid-1');
}

async function pickCustomerAndAddLine() {
  await selectOption('Customer', 'ZZTD01');
  await addPickedLine();
}

function matchRow(row: Record<string, unknown>): Record<string, unknown> {
  const hit = BY_CODE[String(row.product_code)];
  return hit
    ? { ...row, match: 'product', product_id: hit.id, product_set_id: null, product_name: hit.name }
    : { ...row, match: null, product_id: null, product_set_id: null };
}

async function applyExtract(rows: Record<string, unknown>[]) {
  const products = rows.map(matchRow);
  await act(async () => {
    captured.onExtracted?.(products);
  });
  await act(async () => {
    captured.onApply?.({ productLines: products });
  });
}

async function openPriceSection() {
  const opener = screen.queryByRole('button', { name: /^(Price|Preferred Default)/ });
  if (opener && opener.getAttribute('aria-expanded') === 'false') fireEvent.click(opener);
}

describe('PriceTagRequestForm header default (AC-25)', () => {
  it('names the header toggle "Preferred Default"', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    await openPriceSection();
    const group = await screen.findByRole('radiogroup', { name: 'Preferred Default' });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'List price' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Selling price' })).toBeInTheDocument();
  });
});

describe('PriceTagRequestForm copy (AC-23)', () => {
  it('no longer asks to add an item to see the tag before approving', async () => {
    const { container } = render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    expect(screen.queryByText('Add an item to see its tag before approving.')).toBeNull();
    expect(container.textContent).not.toContain('Add an item to see its tag');
  });

  it('does not bring the text back once an item has been removed again', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    await addPickedLine();
    fireEvent.click(screen.getByRole('button', { name: 'Remove line 1' }));
    expect(screen.queryByText(/Add an item to see its tag/)).toBeNull();
  });
});

describe('PriceTagRequestForm per-line price type (AC-19)', () => {
  it('a new line posts the List default', async () => {
    render(<PriceTagRequestForm />);
    await pickCustomerAndAddLine();
    sendToMarketing();
    const payload = await lastCreatePayload();
    expect(payload.price_mode).toBe('list');
    expect(payload.lines[0].price_type).toBe('list');
  });

  it('a line added under Selling posts selling', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    await openPriceSection();
    fireEvent.click(await screen.findByRole('radio', { name: 'Selling price' }));
    await addPickedLine();
    sendToMarketing();
    const payload = await lastCreatePayload();
    expect(payload.price_mode).toBe('selling');
    expect(payload.lines[0].price_type).toBe('selling');
  });

  it('changing the default afterwards does not rewrite a line already added', async () => {
    render(<PriceTagRequestForm />);
    await pickCustomerAndAddLine();
    fireEvent.click(screen.getByRole('radio', { name: 'Selling price' }));
    sendToMarketing();
    const payload = await lastCreatePayload();
    expect(payload.price_mode).toBe('selling');
    expect(payload.lines[0].price_type).toBe('list');
  });

  it('a line switched to SP in a List request posts selling and its typed price', async () => {
    render(<PriceTagRequestForm />);
    await pickCustomerAndAddLine();
    fireEvent.click(screen.getByRole('radio', { name: 'SP' }));
    const input = await screen.findByLabelText('Selling price for line 1');
    fireEvent.change(input, { target: { value: '599' } });
    sendToMarketing();
    const payload = await lastCreatePayload();
    expect(payload.price_mode).toBe('list');
    expect(payload.lines[0].price_type).toBe('selling');
    expect(payload.lines[0].manual_sell_price).toBe(599);
  });

  it('switching a line back to LP drops its typed price from the payload', async () => {
    render(<PriceTagRequestForm />);
    await pickCustomerAndAddLine();
    fireEvent.click(screen.getByRole('radio', { name: 'SP' }));
    fireEvent.change(await screen.findByLabelText('Selling price for line 1'), {
      target: { value: '599' },
    });
    fireEvent.click(screen.getByRole('radio', { name: 'LP' }));
    sendToMarketing();
    const payload = await lastCreatePayload();
    expect(payload.lines[0].price_type).toBe('list');
    expect(payload.lines[0].manual_sell_price == null).toBe(true);
  });
});

describe('PriceTagRequestForm AI extract apply (AC-22)', () => {
  it('applies each matched row price type, defaulting an unmarked one to the header', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    await applyExtract([
      { product_code: P1.code, price_type: 'selling', typed_sell_price: null },
      { product_code: P2.code, price_type: 'list' },
      { product_code: P3.code, price_type: null },
    ]);
    await selectOption('Customer', 'ZZTD01');
    await screen.findByLabelText('Quantity for line 3');
    sendToMarketing();
    const payload = await lastCreatePayload();
    expect(payload.lines.map((l: { price_type: string }) => l.price_type)).toEqual([
      'selling',
      'list',
      'list',
    ]);
  });

  it('a typed SP becomes the manual price on an SP line, with no promotion', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    await applyExtract([{ product_code: P1.code, price_type: 'selling', typed_sell_price: 1729 }]);
    await selectOption('Customer', 'ZZTD01');
    const input = (await screen.findByLabelText('Selling price for line 1')) as HTMLInputElement;
    expect(input.value).toBe('1729');
    sendToMarketing();
    const payload = await lastCreatePayload();
    expect(payload.lines[0].manual_sell_price).toBe(1729);
    expect(payload.lines[0].promotion_id == null).toBe(true);
  });

  it('a typed SP on an LP row is not applied, and a typed LP never is', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    await applyExtract([
      { product_code: P1.code, price_type: 'list', typed_sell_price: 1729, typed_list_price: 2155 },
      { product_code: P2.code, price_type: 'selling', typed_list_price: 2155 },
    ]);
    await selectOption('Customer', 'ZZTD01');
    await screen.findByLabelText('Quantity for line 2');
    sendToMarketing();
    const payload = await lastCreatePayload();
    expect(payload.lines.map((l: { price_type: string }) => l.price_type)).toEqual([
      'list',
      'selling',
    ]);
    expect(payload.lines[0].manual_sell_price == null).toBe(true);
    expect(payload.lines[1].manual_sell_price == null).toBe(true);
  });

  it('a matched set row becomes a combo line with the stored combo id', async () => {
    asMock(lookupProductCombos).mockResolvedValue({
      host_guarded: false,
      combos: [{ combo_id: 'combo-1', name: 'CBF-1234 + CBF-5678', parts: [] }],
    });
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    await applyExtract([
      {
        product_code: P1.code,
        price_type: 'selling',
        typed_sell_price: 1729,
        combo_id: 'combo-1',
        combo_name: 'CBF-1234 + CBF-5678',
        set_parts: [{ product_id: P2.id, product_code: P2.code, product_name: P2.name }],
      },
    ]);
    await selectOption('Customer', 'ZZTD01');
    await screen.findByLabelText('Quantity for line 1');
    sendToMarketing();
    const payload = await lastCreatePayload();
    expect(payload.lines).toHaveLength(1);
    expect(payload.lines[0].combo_id).toBe('combo-1');
    expect(payload.lines[0].price_type).toBe('selling');
    expect(payload.lines[0].manual_sell_price).toBe(1729);
  });

  it('an unmatched set row is not added, and is named in a toast', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    await applyExtract([
      {
        product_code: 'SRTBF11840',
        price_type: 'selling',
        typed_sell_price: 2299,
        combo_id: null,
        set_parts: [],
      },
    ]);
    expect(screen.queryByLabelText('Quantity for line 1')).toBeNull();
    expect(toasts.error).toHaveBeenCalledWith(expect.stringContaining('SRTBF11840'));
  });

  it('a product listed twice becomes one line and the later type wins', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    await applyExtract([
      { product_code: P1.code, price_type: 'list' },
      { product_code: P1.code, price_type: 'selling' },
    ]);
    await selectOption('Customer', 'ZZTD01');
    await screen.findByLabelText('Quantity for line 1');
    expect(screen.queryByLabelText('Quantity for line 2')).toBeNull();
    sendToMarketing();
    const payload = await lastCreatePayload();
    expect(payload.lines).toHaveLength(1);
    expect(payload.lines[0].price_type).toBe('selling');
  });
});
