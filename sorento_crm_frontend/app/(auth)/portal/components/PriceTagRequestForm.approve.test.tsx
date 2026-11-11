/** Owner ruling 3 Nov 14:10: the draft form ends in Approve or Escalate to marketing. */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

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

// The live preview is #2100's and tested there; here it only reports what it
// would: whether a tag is drawn and which items have no template.
const previewReport = vi.hoisted(() => ({ missing: [] as string[], drawn: true, failed: false }));
vi.mock('@/components/dealer-kit/PriceTagLivePreview', async () => {
  const React = await import('react');
  return {
    PriceTagLivePreview: (props: {
      onReadyChange?: (s: { missing: string[]; drawn: boolean; failed: boolean }) => void;
      popup?: { open: boolean; footer?: React.ReactNode };
    }) => {
      const { onReadyChange } = props;
      React.useEffect(() => {
        onReadyChange?.({ ...previewReport });
      }, [onReadyChange]);
      // PRICETAG-REQUEST-LAYOUT: the popup's footer holds Approve.
      return props.popup?.open ? <div data-testid="sheet-popup">{props.popup.footer}</div> : null;
    },
  };
});

vi.mock('./AttachmentDropzone', () => ({
  AttachmentDropzone: () => null,
}));

import {
  createRequest,
  submitAndApprove,
  submitAndEscalate,
  submitRequest,
  lookupTagPreviewForRequest,
  lookupDebtors,
  lookupPromotions,
  lookupTagItems,
} from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';
import { selectOption, chooseTypedItems, approveViaPreview } from '@/test-utils';

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
  chooseTypedItems();
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
  // AC-S1-1/S1-2 (r10): the portal no longer asks who prints - `printBy` is a
  // constant 'self' every payload sends, so there is nothing left to click.
  // Callers keep calling this (kept as a no-op) so the rest of each test body
  // reads the same as it always has.
}


const savedDraft = {
  id: 'req-1',
  lines: [
    {
      id: 'line-1',
      line_type: 'product',
      product_id: 'prod-uuid-1',
      product_set_id: null,
      name: 'ZZT Kitchen Sink',
      code: 'CBF-1234',
      show_promo_price: false,
      quantity: 1,
      included_accessories: null,
      remarks: null,
      sort_order: 0,
      tags: [{ id: 'tag-1', label: '1a', quantity: 1 }],
    },
  ],
};
const tagPreview = {
  lines: [{ line_id: 'line-1', tag_id: 'tag-1', code: 'CBF-1234', name: 'ZZT Kitchen Sink', images: [] }],
  templates: {
    'line-1': {
      id: 'tpl-1',
      name: 'Sink A5',
      family: 'ala_carte',
      doc: { layers: [], width_mm: 80, height_mm: 50 },
      print_size: { width_mm: 80, height_mm: 50 },
    },
  },
  assets: {},
  images: {},
  fonts: [],
};

describe('PriceTagRequestForm - Approve or Escalate, never Submit (owner ruling 3 Nov)', () => {
  beforeEach(() => {
    previewReport.missing = [];
    previewReport.drawn = true;
    previewReport.failed = false;
    asMock(createRequest).mockResolvedValue(savedDraft);
    asMock(lookupTagPreviewForRequest).mockResolvedValue(tagPreview);
  });

  it('offers Save Draft, Escalate to marketing and Preview (Approve inside it), and no Submit', async () => {
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();

    expect(screen.getByRole('button', { name: 'Save Draft' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /escalate to marketing/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Preview' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: /^approve$/i })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Submit' })).toBeNull();
  });

  it('Approve saves the draft and submits and approves it in one call, with the sheet of its own tags', async () => {
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();

    expect(await approveViaPreview()).toBe(true);

    await waitFor(() => expect(submitAndApprove).toHaveBeenCalled());
    const [id, doc] = asMock(submitAndApprove).mock.calls[0];
    expect(id).toBe('req-1');
    const placed = doc.sheets.flatMap((s: { tags: { request_tag_id: string }[] }) => s.tags);
    expect(placed.map((t: { request_tag_id: string }) => t.request_tag_id)).toEqual(['tag-1']);
    expect(submitRequest).not.toHaveBeenCalled();
    expect(toasts.success).toHaveBeenCalledWith('Tag approved');
  });

  it('with an item that has no template, Preview stays clickable; the click says so on the line and opens nothing (owner, 5 + 10 Nov)', async () => {
    previewReport.missing = ['CBF-1234'];
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();

    const approve = screen.getByRole('button', { name: 'Preview' });
    expect(approve).toBeEnabled();
    expect(approve.parentElement).not.toHaveAttribute('title');
    // Nothing is said until the click.
    expect(document.querySelector('[data-error-anchor]')).toBeNull();

    fireEvent.click(approve);

    const anchor = await waitFor(() => {
      const found = document.querySelector('[data-error-anchor="line:0"]');
      expect(found).not.toBeNull();
      return found as Element;
    });
    expect(anchor).toHaveTextContent('No tag template yet.');
    expect(anchor.textContent).not.toMatch(/escalate/i);
    expect(screen.queryByTestId('approve-blocked')).toBeNull();
    expect(screen.queryByTestId('sheet-popup')).toBeNull();
    expect(submitAndApprove).not.toHaveBeenCalled();
  });

  it('A: a line message leaves as soon as its problem is fixed, without another click', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    chooseTypedItems();
    fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    expect(await screen.findByText('Pick a set or a product for this line.')).toBeInTheDocument();

    await selectOption('Search a set or product...', 'product:prod-uuid-1');

    await waitFor(() => expect(screen.queryByText('Pick a set or a product for this line.')).toBeNull());
  });

  it('Escalate does not ask for the facts Approve needs: it is the way out of them', async () => {
    previewReport.missing = ['CBF-1234'];
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /escalate to marketing/i }));

    expect(await screen.findByLabelText('What marketing needs to fix')).toBeInTheDocument();
    expect(document.querySelector('[data-error-anchor]')).toBeNull();
  });

  it('Escalate sends the draft to marketing with the note in one call', async () => {
    previewReport.missing = ['CBF-1234'];
    render(<PriceTagRequestForm />);
    await fillMinimalRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /escalate to marketing/i }));
    fireEvent.change(screen.getByLabelText('What marketing needs to fix'), {
      target: { value: 'Photo is the old model' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send to marketing/i }));

    await waitFor(() =>
      expect(submitAndEscalate).toHaveBeenCalledWith('req-1', 'Photo is the old model'),
    );
    expect(submitRequest).not.toHaveBeenCalled();
    expect(submitAndApprove).not.toHaveBeenCalled();
  });
});
