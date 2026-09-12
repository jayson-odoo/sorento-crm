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
import { act, render, screen, waitFor } from '@testing-library/react';

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

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange?: (v: string) => void;
    placeholder?: string;
  }) => (
    <select
      aria-label={props.id === 'debtor' ? 'Customer' : (props.placeholder ?? '')}
      value={props.value}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
      <option value="" />
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

/** Runs the extraction resolve pass (per-code lookup) and waits for every
 *  code's match to settle before Apply reads them off the ref. */
async function extractAndSettle(products: Record<string, unknown>[]) {
  await act(async () => {
    captured.onExtracted?.(products);
  });
  await waitFor(() => expect(lookupTagItems).toHaveBeenCalledTimes(products.length));
  // Flush the resolved lookup promises' `.then` state updates.
  await act(async () => {
    await Promise.resolve();
  });
}

describe('PriceTagRequestForm - AI extract apply mapping (AC-S6-3, AC-S6-5)', () => {
  it('a matched product row becomes a line with qty defaulted to 1 and remarks from notes', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    const products = [
      {
        product_code: MATCHED_PRODUCT.code,
        product_name: 'Kitchen Sink',
        quantity: null,
        unit_price: 199.5,
        notes: 'For the showroom display',
      },
    ];
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

    const products = [
      {
        product_code: MATCHED_PRODUCT.code,
        quantity: 3.7,
        notes: null,
      },
    ];
    await extractAndSettle(products);

    await act(async () => {
      captured.onApply?.({ productLines: products });
    });

    expect(await screen.findByLabelText('Quantity for line 1')).toHaveValue(4);
  });

  it('a matched SET row becomes a line too, same as a matched product', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    const products = [{ product_code: MATCHED_SET.code, quantity: 1, notes: 'set note' }];
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

    const products = [{ product_code: 'NOT-REAL-CODE', quantity: 2, notes: 'anything' }];
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

    const products = [
      { product_code: MATCHED_PRODUCT.code, quantity: 2, notes: 'first' },
      { product_code: 'GHOST-CODE', quantity: 1, notes: 'second' },
      { product_code: MATCHED_SET.code, quantity: 1, notes: 'third' },
    ];
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

    const products = [{ product_code: MATCHED_PRODUCT.code, quantity: 1, notes: null }];
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

    const products = [{ product_code: MATCHED_PRODUCT.code, quantity: 1, notes: null }];
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
});
