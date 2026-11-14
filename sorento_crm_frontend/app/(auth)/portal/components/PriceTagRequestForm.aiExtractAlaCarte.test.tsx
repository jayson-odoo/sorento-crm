/**
 * PRICETAG-ALA-CARTE (pricetag-ala-carte-acceptance-criteria.md), Upload a file apply
 * (`handleAIExtractApply`): AC-9 a bare product row starts ala carte and the line editor never
 * auto-picks a lone combo onto it; a "+" row matching a stored combo starts on that combo
 * (unchanged). AC-10 rows are never merged into a line by product: each product row is its own
 * line (sets unchanged). Read off the create payload, the same way the LPSP suite does.
 *
 * Written test-FIRST against the UAC; fake codes and prices only.
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
// PRICETAG-REQUEST-LAYOUT: Customers is a multi-select now; its stand-in is a native select
// labelled "Customer" (components/dealer-kit/__mocks__/RequestCustomersSelect.tsx).
vi.mock('@/components/dealer-kit/RequestCustomersSelect');

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

vi.mock('@/components/common/SearchableMultiSelect');

vi.mock('./AttachmentDropzone', () => ({
  AttachmentDropzone: () => null,
}));

type CapturedProps = {
  renderRowStatus?: (p: Record<string, unknown>, i: number) => React.ReactNode;
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
import { selectOption, chooseTypedItems } from '@/test-utils';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const DEBTORS = [{ code: 'ALA-D01', name: 'Ala Dealer' }];
const P1 = { id: 'p-ala-1', code: 'P-ALA-1', name: 'Ala basin' };
const PART = { id: 'p-ala-part', code: 'P-ALA-PART', name: 'Ala tap' };
const SET = { id: 's-ala-1', code: 'S-ALA-1', name: 'Ala set' };

const C = {
  combo_id: 'c-ala-1',
  name: 'P-ALA-1 + P-ALA-PART',
  parts: [
    { product_id: PART.id, code: PART.code, name: PART.name, choice_group: null, is_upgrade: false, topup_amount: null },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  captured = {};
  asMock(lookupDebtors).mockResolvedValue(DEBTORS);
  asMock(lookupPromotions).mockResolvedValue([]);
  asMock(lookupTagItems).mockResolvedValue([]);
  asMock(createRequest).mockResolvedValue({ id: 'req-ala-1' });
  // P-ALA-1 has exactly ONE combo: today's auto-pick would put it on any line that has none.
  asMock(lookupProductCombos).mockImplementation(async (id: string) => ({
    host_guarded: false,
    combos: id === P1.id ? [C] : [],
  }));
});

const bareRow = (notes: string) => ({
  product_code: P1.code,
  match: 'product',
  product_id: P1.id,
  product_set_id: null,
  product_name: P1.name,
  notes,
});
const plusRow = (notes: string) => ({
  ...bareRow(notes),
  combo_id: C.combo_id,
  combo_name: C.name,
  set_parts: [{ product_id: PART.id, product_code: PART.code }],
});
const setRow = (notes: string) => ({
  product_code: SET.code,
  match: 'product_set',
  product_id: null,
  product_set_id: SET.id,
  product_name: SET.name,
  notes,
});

async function applyExtract(rows: Record<string, unknown>[]) {
  await act(async () => {
    captured.onExtracted?.(rows);
  });
  await act(async () => {
    captured.onApply?.({ productLines: rows });
  });
}

/** Lets the line editor's combos lookup answer and land before anything is read. */
async function settleCombos() {
  await waitFor(() => expect(lookupProductCombos).toHaveBeenCalledWith(P1.id));
  await act(async () => {
    await new Promise((r) => setTimeout(r, 30));
  });
}

function sendToMarketing() {
  if (!screen.queryByLabelText('What marketing needs to fix')) {
    fireEvent.click(screen.getByRole('button', { name: /escalate to marketing/i }));
  }
  fireEvent.change(screen.getByLabelText('What marketing needs to fix'), {
    target: { value: 'Please check' },
  });
  fireEvent.click(screen.getByRole('button', { name: /send to marketing/i }));
}

type SentLine = { product_id: string | null; product_set_id: string | null; combo_id: string | null; remarks: string | null };

async function sentLines(): Promise<SentLine[]> {
  await selectOption('Customer', 'ALA-D01');
  chooseTypedItems();
  await screen.findByLabelText('Quantity for line 1');
  await settleCombos();
  sendToMarketing();
  await waitFor(() => expect(createRequest).toHaveBeenCalled());
  return asMock(createRequest).mock.calls.at(-1)?.[0].lines;
}

describe('AC-9 a bare product row starts ala carte', () => {
  it('a bare row of a one-combo product is sent ala carte (combo_id null), after the combos lookup answered', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    await applyExtract([bareRow('bare')]);
    const lines = await sentLines();
    expect(lines).toHaveLength(1);
    expect(lines[0].product_id).toBe(P1.id);
    expect(lines[0].combo_id ?? null).toBeNull();
  });

  it('a "+" row matching the stored combo is sent on that combo (unchanged)', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    await applyExtract([plusRow('plus')]);
    const lines = await sentLines();
    expect(lines).toHaveLength(1);
    expect(lines[0].combo_id).toBe(C.combo_id);
  });
});

describe('AC-10 rows are never merged into a line by product', () => {
  it('a bare row and a "+" row of the same product become two lines: ala carte and the combo', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    await applyExtract([bareRow('bare'), plusRow('plus')]);
    const lines = await sentLines();
    expect(lines.map((l) => [l.product_id, l.combo_id ?? null, l.remarks])).toEqual([
      [P1.id, null, 'bare'],
      [P1.id, C.combo_id, 'plus'],
    ]);
  });

  it('two bare rows of the same product become two ala carte lines', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    await applyExtract([bareRow('first'), bareRow('second')]);
    const lines = await sentLines();
    expect(lines.map((l) => [l.product_id, l.combo_id ?? null, l.remarks])).toEqual([
      [P1.id, null, 'first'],
      [P1.id, null, 'second'],
    ]);
  });

  it('a row of a product already on the request adds its own line instead of merging into it', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    await applyExtract([bareRow('first')]);
    await applyExtract([bareRow('second')]);
    const lines = await sentLines();
    expect(lines.map((l) => l.remarks)).toEqual(['first', 'second']);
  });

  it('sets keep today\'s merge: the same set twice is one line (unchanged)', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    await applyExtract([setRow('a'), setRow('b')]);
    await selectOption('Customer', 'ALA-D01');
    chooseTypedItems();
    await screen.findByLabelText('Quantity for line 1');
    expect(screen.queryByLabelText('Quantity for line 2')).toBeNull();
  });
});
