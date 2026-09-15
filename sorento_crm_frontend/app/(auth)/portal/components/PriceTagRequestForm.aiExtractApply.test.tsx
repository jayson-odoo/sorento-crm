/**
 * AI extract apply mapping (D7, AC-S6-3, AC-S6-5).
 *
 * The mapping lives inline in `PriceTagRequestForm` (`handleAIExtractApply` /
 * `handleAIExtracted`), not as an exported pure function, so this drives it
 * through the component with `AIExtractDialog` mocked to a prop-capturing
 * stub - the same "test through the component with the dialog mocked" shape
 * the sibling `.lines.test.tsx` / `.validation.test.tsx` files use for their
 * own dependencies. `AIExtractDialog` mounts unconditionally in the real
 * component (only its `open` prop is gated on the trigger button), so the
 * captured `onExtracted`/`onApply` callbacks are reachable without first
 * getting a file attached.
 *
 * Apply = one line per MATCHED row, qty defaults to 1, remarks come from the
 * extracted row's `notes`; an unmatched code is skipped and named in a toast.
 * `unit_price` is never read onto a line (ADR 0008).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

vi.mock('../lib/price-tag-request-service', () => ({
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
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange?: (v: string) => void;
    placeholder?: string;
    // S1 (code review): the Item picker's own selected-value label - the
    // only surface this mock exposes for asserting what NAME a picked line
    // reads, since the mock otherwise renders no text for it.
    selectedOption?: { value: string; label: string };
  }) => (
    <select
      aria-label={props.id === 'debtor' ? 'Customer' : (props.placeholder ?? '')}
      value={props.value}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
      <option value="" />
      {props.selectedOption && (
        <option value={props.selectedOption.value}>{props.selectedOption.label}</option>
      )}
    </select>
  ),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: { disabled?: boolean }) => (
    <select multiple aria-label="Alternatives" disabled={props.disabled} onChange={() => {}} />
  ),
}));

let capturedPendingFiles: File[] = [];
vi.mock('./AttachmentDropzone', () => ({
  AttachmentDropzone: (props: { pendingFiles?: File[] }) => {
    capturedPendingFiles = props.pendingFiles ?? [];
    return null;
  },
}));

type CapturedProps = {
  fieldDefs?: unknown[];
  onExtracted?: (products: unknown[]) => void;
  onApply?: (payload: {
    productLines: unknown[];
    files?: File[];
    alsoAttach?: boolean;
    values?: Record<string, unknown>;
  }) => void;
  renderRowStatus?: (p: Record<string, unknown>) => React.ReactNode;
};
let captured: CapturedProps = {};
vi.mock('./AIExtractDialog', () => ({
  AIExtractDialog: (props: CapturedProps) => {
    captured = props;
    return null;
  },
}));

import { lookupDebtors, lookupTagItems } from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const MATCHED_PRODUCT = {
  kind: 'product' as const,
  id: 'prod-uuid-1',
  code: 'CBF-1234',
  name: 'ZZT Kitchen Sink',
};
const MATCHED_SET = {
  kind: 'product_set' as const,
  id: 'set-uuid-1',
  code: 'ZZTSET-1',
  name: 'ZZT Bathroom Set',
};

beforeEach(() => {
  vi.clearAllMocks();
  captured = {};
  capturedPendingFiles = [];
  asMock(lookupDebtors).mockResolvedValue([]);
  asMock(lookupTagItems).mockImplementation(async (query?: string) => {
    const q = (query ?? '').trim().toLowerCase();
    if (q === MATCHED_PRODUCT.code.toLowerCase()) return [MATCHED_PRODUCT];
    if (q === MATCHED_SET.code.toLowerCase()) return [MATCHED_SET];
    return [];
  });
});

// The lines table (where "Quantity for line N" / "Remarks for line N" render)
// lives inside the "Sales Order & Lines" section (D-P1), collapsed by
// default - no customer is picked in these tests, so it never auto-opens
// (AC-P3), and Radix's Collapsible unmounts its content while closed.
function openSalesOrderSection() {
  fireEvent.click(screen.getByRole('button', { name: /Sales Order & Lines/ }));
}

/**
 * One matcher (D1/D3, PLAN-price-tag-ai-extract-resolver.md): the extract
 * already resolved every code through the shared entity resolver
 * server-side, so a fixture builds the SAME `match` / `product_id` /
 * `product_set_id` fields the real payload always carries now, instead of
 * leaving the form to look the code up itself - there is no lookup left to
 * wait for.
 */
function withMatch(product: Record<string, unknown>): Record<string, unknown> {
  const code = String(product.product_code ?? '');
  if (code === MATCHED_PRODUCT.code) {
    return { ...product, match: 'product', product_id: MATCHED_PRODUCT.id, product_set_id: null };
  }
  if (code === MATCHED_SET.code) {
    return {
      ...product,
      match: 'product_set',
      product_id: null,
      product_set_id: MATCHED_SET.id,
    };
  }
  return { ...product, match: null, product_id: null, product_set_id: null };
}

/** Runs the extraction resolve pass and flushes the state update it makes. */
async function extractAndSettle(products: Record<string, unknown>[]) {
  await act(async () => {
    captured.onExtracted?.(products);
  });
}

describe('PriceTagRequestForm - AI extract apply mapping (AC-S6-3, AC-S6-5)', () => {
  it('a matched product row becomes a line with qty defaulted to 1 and remarks from notes', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    openSalesOrderSection();

    const products = [
      {
        product_code: MATCHED_PRODUCT.code,
        product_name: 'Kitchen Sink',
        quantity: null,
        unit_price: 199.5,
        notes: 'For the showroom display',
      },
    ].map(withMatch);
    await extractAndSettle(products);

    await act(async () => {
      captured.onApply?.({ productLines: products });
    });

    expect(await screen.findByLabelText('Quantity for line 1')).toHaveValue(1);
    expect(screen.getByLabelText('Remarks for line 1')).toHaveValue(
      'For the showroom display',
    );
  });

  it('quantity from the extracted row is rounded and floored at 1, not defaulted', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    openSalesOrderSection();

    const products = [
      {
        product_code: MATCHED_PRODUCT.code,
        quantity: 3.7,
        notes: null,
      },
    ].map(withMatch);
    await extractAndSettle(products);

    await act(async () => {
      captured.onApply?.({ productLines: products });
    });

    expect(await screen.findByLabelText('Quantity for line 1')).toHaveValue(4);
  });

  it('a matched SET row becomes a line too, same as a matched product', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    openSalesOrderSection();

    const products = [{ product_code: MATCHED_SET.code, quantity: 1, notes: 'set note' }].map(
      withMatch,
    );
    await extractAndSettle(products);

    await act(async () => {
      captured.onApply?.({ productLines: products });
    });

    expect(await screen.findByLabelText('Quantity for line 1')).toHaveValue(1);
    expect(screen.getByLabelText('Remarks for line 1')).toHaveValue('set note');
  });

  it('an unmatched code is skipped and named in a toast, not added as a line', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    const products = [{ product_code: 'NOT-REAL-CODE', quantity: 2, notes: 'anything' }].map(
      withMatch,
    );
    await extractAndSettle(products);

    await act(async () => {
      captured.onApply?.({ productLines: products });
    });

    expect(screen.queryByLabelText('Quantity for line 1')).toBeNull();
    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith(
        expect.stringContaining('NOT-REAL-CODE'),
      ),
    );
  });

  it('a mixed batch appends only the matched rows, in order, and reports the rest', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    openSalesOrderSection();

    const products = [
      { product_code: MATCHED_PRODUCT.code, quantity: 2, notes: 'first' },
      { product_code: 'GHOST-CODE', quantity: 1, notes: 'second' },
      { product_code: MATCHED_SET.code, quantity: 1, notes: 'third' },
    ].map(withMatch);
    await extractAndSettle(products);

    await act(async () => {
      captured.onApply?.({ productLines: products });
    });

    expect(await screen.findByLabelText('Quantity for line 1')).toHaveValue(2);
    expect(screen.getByLabelText('Remarks for line 1')).toHaveValue('first');
    expect(screen.getByLabelText('Quantity for line 2')).toHaveValue(1);
    expect(screen.getByLabelText('Remarks for line 2')).toHaveValue('third');
    expect(screen.queryByLabelText('Quantity for line 3')).toBeNull();
    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith(expect.stringContaining('GHOST-CODE')),
    );
  });

  it('honours alsoAttach: the extracted files join the Sales Order pending files (review fix)', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    openSalesOrderSection();

    const products = [{ product_code: MATCHED_PRODUCT.code, quantity: 1, notes: null }].map(
      withMatch,
    );
    await extractAndSettle(products);
    const file = new File(['zzt'], 'ZZT-so.pdf', { type: 'application/pdf' });

    await act(async () => {
      captured.onApply?.({ productLines: products, files: [file], alsoAttach: true });
    });

    await waitFor(() => expect(capturedPendingFiles).toContain(file));
  });

  it('does not buffer the file when alsoAttach is false', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    const products = [{ product_code: MATCHED_PRODUCT.code, quantity: 1, notes: null }].map(
      withMatch,
    );
    await extractAndSettle(products);
    const file = new File(['zzt'], 'ZZT-so.pdf', { type: 'application/pdf' });

    await act(async () => {
      captured.onApply?.({ productLines: products, files: [file], alsoAttach: false });
    });

    expect(capturedPendingFiles).not.toContain(file);
  });

  it('passes no field defs to mirror (D7 review push-back: no header fields on this form)', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    expect(captured.fieldDefs).toEqual([]);
  });

  it('removing a row in the dialog does not shift the index-based match mapping (review round 2)', async () => {
    // handleAIExtractApply reads `aiMatchesRef.current[index]` using the
    // INDEX INTO WHATEVER ARRAY THE DIALOG HANDS BACK on Apply - but that
    // ref was built by handleAIExtracted off the ORIGINAL, unfiltered
    // extraction result. Removing a row in the dialog (D-P4) shortens the
    // array Apply sends without shortening the ref, so every match after the
    // removed row reads the WRONG entry.
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    openSalesOrderSection();

    const extracted = [
      { product_code: MATCHED_PRODUCT.code, quantity: 1, notes: 'first' },
      { product_code: 'GHOST-CODE', quantity: 1, notes: 'not found' },
      { product_code: MATCHED_SET.code, quantity: 5, notes: 'set of five' },
    ].map(withMatch);
    await extractAndSettle(extracted);

    // The dialog removes row 2 (GHOST-CODE, an "x" per D-P4) locally, then
    // Confirm and prefill calls onApply with only the remaining rows.
    const afterRemovingGhostRow = [extracted[0], extracted[2]];

    await act(async () => {
      captured.onApply?.({ productLines: afterRemovingGhostRow });
    });

    expect(await screen.findByLabelText('Quantity for line 1')).toHaveValue(1);
    expect(screen.getByLabelText('Remarks for line 1')).toHaveValue('first');
    expect(screen.getByLabelText('Quantity for line 2')).toHaveValue(5);
    expect(screen.getByLabelText('Remarks for line 2')).toHaveValue('set of five');
    expect(screen.queryByLabelText('Quantity for line 3')).toBeNull();
    expect(toasts.error).not.toHaveBeenCalled();
  });

  it('R3-7/AC-R12: the same product extracted twice merges into ONE line with summed quantity', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    openSalesOrderSection();

    const products = [
      { product_code: MATCHED_PRODUCT.code, quantity: 2, notes: 'first mention' },
      { product_code: MATCHED_PRODUCT.code, quantity: 3, notes: 'second mention' },
    ].map(withMatch);
    await extractAndSettle(products);

    await act(async () => {
      captured.onApply?.({ productLines: products });
    });

    expect(await screen.findByLabelText('Quantity for line 1')).toHaveValue(5);
    expect(screen.queryByLabelText('Quantity for line 2')).toBeNull();
  });
});

/**
 * AC-S1-6, AC-S1-7 (PLAN-price-tag-ai-extract-resolver, D3): the extract now
 * arrives already resolved - `match` / `product_id` / `product_set_id` ride
 * on each extracted row - so the form reads the payload directly instead of
 * calling `lookupTagItems` per code and comparing codes itself.
 */
describe('PriceTagRequestForm - AI extract reads match fields off the payload (AC-S1-6, AC-S1-7)', () => {
  it('AC-S1-6: statuses render from match/product_id/product_set_id alone; lookupTagItems is never called', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    const products = [
      {
        product_code: MATCHED_PRODUCT.code,
        product_name: MATCHED_PRODUCT.name,
        match: 'product',
        product_id: MATCHED_PRODUCT.id,
        product_set_id: null,
        quantity: 1,
        notes: null,
      },
      {
        product_code: MATCHED_SET.code,
        product_name: MATCHED_SET.name,
        match: 'product_set',
        product_id: null,
        product_set_id: MATCHED_SET.id,
        quantity: 1,
        notes: null,
      },
      {
        product_code: 'GHOST-CODE',
        product_name: null,
        match: null,
        product_id: null,
        product_set_id: null,
        quantity: 1,
        notes: null,
      },
    ];

    await act(async () => {
      captured.onExtracted?.(products);
    });

    // The whole point of D3: no per-code round trip during extract.
    expect(lookupTagItems).not.toHaveBeenCalled();

    const { getByTestId } = render(
      <div>
        <div data-testid="row-0">{captured.renderRowStatus?.(products[0])}</div>
        <div data-testid="row-1">{captured.renderRowStatus?.(products[1])}</div>
        <div data-testid="row-2">{captured.renderRowStatus?.(products[2])}</div>
      </div>,
    );

    expect(within(getByTestId('row-0')).getByText('Matched product')).toBeTruthy();
    expect(within(getByTestId('row-1')).getByText('Matched set')).toBeTruthy();
    expect(within(getByTestId('row-2')).getByText('Not found')).toBeTruthy();
  });

  it('AC-S1-7: Apply adds a line for every matched row and toasts the rest, with no wait for a lookup', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    openSalesOrderSection();

    const products = [
      {
        product_code: MATCHED_PRODUCT.code,
        product_name: MATCHED_PRODUCT.name,
        match: 'product',
        product_id: MATCHED_PRODUCT.id,
        product_set_id: null,
        quantity: 2,
        notes: 'first',
      },
      {
        product_code: 'GHOST-CODE',
        product_name: null,
        match: null,
        product_id: null,
        product_set_id: null,
        quantity: 1,
        notes: 'second',
      },
      {
        product_code: MATCHED_SET.code,
        product_name: MATCHED_SET.name,
        match: 'product_set',
        product_id: null,
        product_set_id: MATCHED_SET.id,
        quantity: 1,
        notes: 'third',
      },
    ];

    await act(async () => {
      captured.onExtracted?.(products);
    });
    // Matches must already be available synchronously off the payload -
    // Apply is called with no `extractAndSettle`/lookup wait in between.
    expect(lookupTagItems).not.toHaveBeenCalled();

    await act(async () => {
      captured.onApply?.({ productLines: products });
    });

    expect(await screen.findByLabelText('Quantity for line 1')).toHaveValue(2);
    expect(screen.getByLabelText('Remarks for line 1')).toHaveValue('first');
    expect(screen.getByLabelText('Quantity for line 2')).toHaveValue(1);
    expect(screen.getByLabelText('Remarks for line 2')).toHaveValue('third');
    expect(screen.queryByLabelText('Quantity for line 3')).toBeNull();
    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith(expect.stringContaining('GHOST-CODE')),
    );
  });

  // S1 (code review): a resolved match's product_name is the CRM's own name
  // (the backend now overrides it there, ai_extract_resolver_match.py pins
  // that half), never the sales order's freeform description - the applied
  // line's Item is what marketing/the salesperson read back.
  it("S1: the applied line's Item reads the CRM name from a resolved match", async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    openSalesOrderSection();

    const products = [
      {
        product_code: MATCHED_PRODUCT.code,
        product_name: MATCHED_PRODUCT.name,
        match: 'product',
        product_id: MATCHED_PRODUCT.id,
        product_set_id: null,
        quantity: 1,
        notes: null,
      },
    ];

    await act(async () => {
      captured.onExtracted?.(products);
    });
    await act(async () => {
      captured.onApply?.({ productLines: products });
    });

    await screen.findByLabelText('Quantity for line 1');
    expect(screen.getByText(MATCHED_PRODUCT.name)).toBeInTheDocument();
  });
});
