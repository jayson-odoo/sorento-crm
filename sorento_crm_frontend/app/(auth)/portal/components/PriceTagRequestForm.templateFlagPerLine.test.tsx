/**
 * PRICETAG-ALA-CARTE fix round: "No tag template yet." belongs to the LINE that has no template,
 * not to every line of the same product.
 *
 * Defect (crew browser pass): one request holds the same product on three lines - LP ala carte,
 * LP on its combo, SP ala carte. The product has an LP template, no SP template. The live preview
 * reports the missing lines by product CODE, and the form flags a line when its code is in that
 * list, so all three lines read "No tag template yet." and Preview/Approve is refused for all.
 *
 * Expected: only the SP line is flagged. The live preview names the missing line by its line KEY
 * (assumed field on the `onReadyChange` state: `missingKeys: string[]`), so two lines with the
 * same code are distinguishable.
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). Harness as `PriceTagRequestForm.lpsp.test.tsx`
 * (service mocked, SearchableSelect stubbed, AI dialog captured to build the three lines), but
 * the REAL PriceTagLivePreview runs against a mocked `lookupTagPreview`.
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
    lookupTagPreview: vi.fn(),
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
  fetchMe: vi.fn().mockResolvedValue({ visible_form_types: ['price_tag_request'] }),
}));

vi.mock('@/components/dealer-kit/RequestCustomersSelect');

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange?: (v: string) => void;
    onOptionChange?: (o: { value: string; label: string; description?: string } | null) => void;
    options?: { value: string; label: string; description?: string }[];
    fetchOptions?: (q: string) => Promise<{ value: string; label: string; description?: string }[]>;
    placeholder?: string;
  }) => {
    const [async, setAsync] = React.useState<{ value: string; label: string; description?: string }[]>([]);
    React.useEffect(() => {
      if (props.fetchOptions) void props.fetchOptions('').then(setAsync);
    }, [props.fetchOptions]);
    const options = props.options ?? async;
    const ariaLabel =
      props.id === 'debtor' ? 'Customer' : props.id === 'promotion' ? 'Promotion' : (props.placeholder ?? '');
    return (
      <select
        aria-label={ariaLabel}
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

vi.mock('@/components/common/SearchableMultiSelect');

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
  lookupTagPreview,
} from '../lib/price-tag-request-service';
import type { TagPreviewLineInput, TagPreviewResponse } from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';
import { PriceTagLivePreview } from '@/components/dealer-kit/PriceTagLivePreview';
import { emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import { selectOption, chooseTypedItems } from '@/test-utils';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const P1 = { id: 'prod-uuid-1', code: 'CBF-1234', name: 'ZZT Kitchen Sink' };
const P2 = { id: 'prod-uuid-2', code: 'CBF-5678', name: 'ZZT Basin' };
const NO_TEMPLATE = 'No tag template yet.';

const LP_TEMPLATE = {
  id: 'tpl-lp',
  name: 'Sink LP A5',
  family: 'ala_carte',
  doc: { layers: [], width_mm: 80, height_mm: 50 },
  print_size: { width_mm: 80, height_mm: 50 },
};

/**
 * The server's answer: every line of the product resolves to the same code; only a line drawn at
 * list price has a template (the product has an LP template, no SP one).
 */
function previewAnswer(mode: string, sent: TagPreviewLineInput[]): TagPreviewResponse {
  return {
    lines: sent.map((l) => ({ line_id: l.key, tag_id: l.key, code: P1.code, name: P1.name, images: [] })),
    templates: Object.fromEntries(
      sent.filter((l) => (l.price_type ?? mode) !== 'selling').map((l) => [l.key, LP_TEMPLATE]),
    ),
    assets: {},
    images: {},
    fonts: [],
  } as unknown as TagPreviewResponse;
}

const part = (product: { id: string; code: string; name: string }) => ({
  product_id: product.id,
  code: product.code,
  name: product.name,
  choice_group: null,
  is_upgrade: false,
  topup_amount: null,
});

beforeEach(() => {
  vi.clearAllMocks();
  captured = {};
  asMock(lookupDebtors).mockResolvedValue([{ code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' }]);
  asMock(lookupPromotions).mockResolvedValue([]);
  asMock(lookupTagItems).mockResolvedValue([{ kind: 'product', ...P1 }]);
  asMock(createRequest).mockResolvedValue({ id: 'req-1' });
  asMock(lookupProductCombos).mockResolvedValue({
    host_guarded: false,
    combos: [
      { combo_id: 'combo-a', name: 'Combo A', parts: [] },
      { combo_id: 'combo-b', name: 'CBF-1234 + CBF-5678', parts: [part(P2)] },
    ],
  });
  asMock(lookupTagPreview).mockImplementation(async (mode: string, sent: TagPreviewLineInput[]) =>
    previewAnswer(mode, sent),
  );
});

/** Three lines of ONE product: LP ala carte, LP on its combo, SP ala carte. */
async function threeLinesOfOneProduct() {
  render(<PriceTagRequestForm />);
  await screen.findByLabelText('Customer');
  const rows = [
    { product_code: P1.code, price_type: 'list' },
    {
      product_code: P1.code,
      price_type: 'list',
      combo_id: 'combo-b',
      combo_name: 'CBF-1234 + CBF-5678',
      set_parts: [{ product_id: P2.id, product_code: P2.code }],
    },
    { product_code: P1.code, price_type: 'selling' },
  ].map((row) => ({ ...row, match: 'product', product_id: P1.id, product_set_id: null, product_name: P1.name }));
  await act(async () => {
    captured.onExtracted?.(rows);
  });
  await act(async () => {
    captured.onApply?.({ productLines: rows });
  });
  await selectOption('Customer', 'ZZTD01');
  chooseTypedItems();
  await screen.findByLabelText('Quantity for line 3');
}

/** Wait until the live preview has asked about all three lines and its answer has landed. */
async function previewSettled() {
  await waitFor(
    () => {
      const calls = asMock(lookupTagPreview).mock.calls;
      expect(calls.length).toBeGreaterThan(0);
      const sent = calls.at(-1)?.[1] as TagPreviewLineInput[];
      expect(sent).toHaveLength(3);
      expect(sent.map((l) => l.price_type)).toEqual(['list', 'list', 'selling']);
    },
    { timeout: 3000 },
  );
  await act(async () => {
    await asMock(lookupTagPreview).mock.results.at(-1)?.value;
  });
}

function anchorText(index: number): string {
  return document.querySelector(`[data-error-anchor="line:${index}"]`)?.textContent ?? '';
}

describe('PriceTagRequestForm: a missing template flags its own line only (PRICETAG-ALA-CARTE)', () => {
  it('the setup holds three lines of the same product and the preview misses only the SP line', async () => {
    await threeLinesOfOneProduct();
    await previewSettled();
    const [mode, sent] = asMock(lookupTagPreview).mock.calls.at(-1) as [string, TagPreviewLineInput[]];
    expect(sent.every((l) => l.product_id === P1.id)).toBe(true);
    expect(sent.map((l) => l.combo_id ?? null)).toEqual([null, 'combo-b', null]);
    expect(Object.keys(previewAnswer(mode, sent).templates)).toEqual([sent[0].key, sent[1].key]);
  });

  it('Preview flags only the SP line "No tag template yet."; the two LP lines of the same product are not', async () => {
    await threeLinesOfOneProduct();
    await previewSettled();

    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));

    await waitFor(() => expect(anchorText(2)).toContain(NO_TEMPLATE));
    expect(anchorText(0)).not.toContain(NO_TEMPLATE);
    expect(anchorText(1)).not.toContain(NO_TEMPLATE);
    expect(screen.getAllByText(NO_TEMPLATE)).toHaveLength(1);
  });
});

// --------------------------------------------------------------------------- unit: the report
const line = (patch: Partial<DraftLine>): DraftLine => ({ ...emptyDraftLine(), ...patch });

describe('PriceTagLivePreview reports a missing template by line key (assumed field: missingKeys)', () => {
  it('names the SP line key, not the two LP lines that share its code', async () => {
    const onReadyChange = vi.fn();
    const lines = [
      line({ key: 'lp-ala', product_id: P1.id, code: P1.code, price_type: 'list' }),
      line({ key: 'lp-combo', product_id: P1.id, code: P1.code, price_type: 'list', combo_id: 'combo-b' }),
      line({ key: 'sp-ala', product_id: P1.id, code: P1.code, price_type: 'selling' }),
    ];
    const lookup = vi.fn(async (mode: string, sent: TagPreviewLineInput[]) => previewAnswer(mode, sent));
    render(
      <PriceTagLivePreview
        lines={lines}
        priceMode="list"
        lookupTagPreview={lookup as never}
        onReadyChange={onReadyChange}
        popup={{ open: false, onClose: vi.fn() }}
      />,
    );
    await waitFor(() => expect(lookup).toHaveBeenCalled(), { timeout: 3000 });
    await waitFor(() =>
      expect(onReadyChange).toHaveBeenLastCalledWith(expect.objectContaining({ drawn: true, failed: false })),
    );
    const state = onReadyChange.mock.calls.at(-1)?.[0] as { missingKeys?: string[] };
    expect(state.missingKeys).toEqual(['sp-ala']);
  });
});
