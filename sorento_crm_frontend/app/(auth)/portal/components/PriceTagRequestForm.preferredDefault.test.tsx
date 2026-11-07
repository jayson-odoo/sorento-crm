/**
 * PRICETAG-COMBO-FORMAT fix round 1, R7: flipping the request's "Preferred Default" re-picks the
 * template of every line that has no type of its own (it follows the header), to the new type's
 * default; a line the user typed LP / SP keeps its own type and template.
 *
 * Written test-FIRST: the header flip changes `price_mode` only, so a following line keeps the
 * template it had for the old type (and the payload carries it).
 * Harness: `PriceTagRequestForm.lpsp.test.tsx` plus `lookupProductTagTemplates`.
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
  lookupProductTagTemplates: vi.fn(),
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
  lookupLinePricing,
  lookupProductTagTemplates,
  lookupPromotions,
  lookupTagItems,
  lookupProductCombos,
} from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';
import { selectOption } from '@/test-utils';


const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const DEBTORS = [{ code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' }];
const ITEMS = [{ kind: 'product' as const, id: 'prod-uuid-1', code: 'CBF-1234', name: 'ZZT Kitchen Sink' }];

const tpl = (id: string, price_type: string, flags: { l?: boolean; s?: boolean }) => ({
  id,
  name: `Tpl ${id}`,
  family: 'ala_carte',
  published: true,
  width_mm: 80,
  height_mm: 50,
  price_type,
  default_list: !!flags.l,
  default_selling: !!flags.s,
});

beforeEach(() => {
  vi.clearAllMocks();
  captured = {};
  asMock(lookupDebtors).mockResolvedValue(DEBTORS);
  asMock(lookupPromotions).mockResolvedValue([]);
  asMock(lookupTagItems).mockResolvedValue(ITEMS);
  asMock(createRequest).mockResolvedValue({ id: 'req-1' });
  asMock(lookupProductTagTemplates).mockResolvedValue([
    tpl('lp', 'list', { l: true }),
    tpl('sp', 'selling', { s: true }),
  ]);
});

function sendToMarketing() {
  if (!screen.queryByLabelText('What marketing needs to fix')) {
    fireEvent.click(screen.getByRole('button', { name: /escalate to marketing/i }));
  }
  fireEvent.change(screen.getByLabelText('What marketing needs to fix'), { target: { value: 'Please check' } });
  fireEvent.click(screen.getByRole('button', { name: /send to marketing/i }));
}

async function lineWithTemplates() {
  render(<PriceTagRequestForm />);
  await selectOption('Customer', 'ZZTD01');
  fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ }));
  fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
  await selectOption('Search a set or product...', 'product:prod-uuid-1');
  // The List default: only the LP template fits, so it is the line's template.
  await screen.findByText('Template: Tpl lp');
}

describe('Preferred Default flip re-picks templates (R7)', () => {
  it('R7: a line that follows the header moves to the SP default when the header flips to Selling', async () => {
    await lineWithTemplates();
    fireEvent.click(screen.getByRole('radio', { name: 'Selling price' }));
    await screen.findByText('Template: Tpl sp');
    sendToMarketing();
    await waitFor(() => expect(createRequest).toHaveBeenCalled());
    const line = asMock(createRequest).mock.calls.at(-1)?.[0].lines[0];
    expect(line.price_type).toBe('selling');
    expect(line.tag_template_id).toBe('sp');
  });

  it('R7: a line the user typed LP keeps its type and template when the header flips', async () => {
    await lineWithTemplates();
    fireEvent.click(screen.getByRole('radio', { name: 'SP' }));
    fireEvent.click(screen.getByRole('radio', { name: 'LP' }));
    await screen.findByText('Template: Tpl lp');
    fireEvent.click(screen.getByRole('radio', { name: 'Selling price' }));
    sendToMarketing();
    await waitFor(() => expect(createRequest).toHaveBeenCalled());
    const line = asMock(createRequest).mock.calls.at(-1)?.[0].lines[0];
    expect(line.price_type).toBe('list');
    expect(line.tag_template_id).toBe('lp');
  });
});
