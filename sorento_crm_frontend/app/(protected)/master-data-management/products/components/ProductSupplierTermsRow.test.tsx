/**
 * The row where a buyer puts a price on a product.
 *
 * The plan's "No price yet" section exists because 5,417 product-supplier links carry no
 * price. This row is the only place one can be entered, so what it must get right is the
 * price / currency pairing: a yuan figure saved with no currency code is read as ringgit
 * everywhere downstream and nothing can detect it afterwards.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ProductSupplier } from '../../../procurement-management/product-suppliers/types/productSupplier.types';
import {
  ProductSupplierTermsRow,
  draftToPatch,
  termsError,
  type SupplierTermsDraft,
} from './ProductSupplierTermsRow';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

const CURRENCIES = [
  { value: 'MYR', label: 'MYR' },
  { value: 'CNY', label: 'CNY' },
];

function link(over: Partial<ProductSupplier> = {}): ProductSupplier {
  return {
    id: 'ps-1',
    product_id: 'prod-1',
    supplier_id: 'sup-1',
    standard_lead_time_days: 45,
    created_at: new Date(),
    supplier: { id: 'sup-1', supplier_code: 'SUP-1', supplier_name: 'Acme Tiles' },
    ...over,
  } as ProductSupplier;
}

function renderRow(ps: ProductSupplier, onSave = vi.fn(), onRemove = vi.fn(async () => {})) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(ProductSupplierTermsRow, {
        ps,
        currencyOptions: CURRENCIES,
        onSave,
        onRemove,
        isSaving: false,
        isDeleting: false,
      }),
    ),
  );
  return { onSave, onRemove };
}

beforeEach(() => vi.clearAllMocks());

describe('ProductSupplierTermsRow - what it shows', () => {
  it('shows every term the reorder plan reads', () => {
    renderRow(link({ unit_cost: 12.5, currency: 'CNY', moq: 100, order_multiple: 25 }));
    expect((screen.getByLabelText('Lead time (days)') as HTMLInputElement).value).toBe('45');
    expect((screen.getByLabelText('Unit cost') as HTMLInputElement).value).toBe('12.5');
    expect((screen.getByLabelText('Minimum order') as HTMLInputElement).value).toBe('100');
    expect((screen.getByLabelText('Order multiple') as HTMLInputElement).value).toBe('25');
    expect(screen.getByText('CNY')).toBeInTheDocument();
  });

  it('leaves a term that has never been set blank, not zero', () => {
    // Zero is a decision ("no minimum") and blank is its absence. Rendering blank as 0
    // would put a number on the record that nobody chose.
    renderRow(link({ unit_cost: null, moq: null }));
    expect((screen.getByLabelText('Unit cost') as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText('Minimum order') as HTMLInputElement).value).toBe('');
  });

  it('offers Save only once something has changed', () => {
    renderRow(link());
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
    fireEvent.change(screen.getByLabelText('Minimum order'), { target: { value: '50' } });
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
  });
});

describe('ProductSupplierTermsRow - a price has to say what money it is in', () => {
  it('refuses to save a price with no currency, and says why', () => {
    const { onSave } = renderRow(link({ unit_cost: null, currency: null }));
    fireEvent.change(screen.getByLabelText('Unit cost'), { target: { value: '12.5' } });

    expect(screen.getByRole('alert')).toHaveTextContent(/currency/i);
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('saves once the currency is chosen', () => {
    const { onSave } = renderRow(link({ unit_cost: 12.5, currency: 'CNY' }));
    fireEvent.change(screen.getByLabelText('Unit cost'), { target: { value: '13' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ unit_cost: '13', currency: 'CNY' }));
  });
});

describe('ProductSupplierTermsRow - removing a supplier', () => {
  it('asks before unlinking, and only then calls through', () => {
    const { onRemove } = renderRow(link());
    fireEvent.click(screen.getByRole('button', { name: /Remove Acme Tiles/i }));
    expect(screen.getByText('Confirm delete')).toBeInTheDocument();
    expect(onRemove).not.toHaveBeenCalled();
  });
});

describe('draftToPatch / termsError', () => {
  const draft = (over: Partial<SupplierTermsDraft> = {}): SupplierTermsDraft => ({
    standard_lead_time_days: '45',
    unit_cost: '',
    currency: '',
    moq: '',
    order_multiple: '',
    ...over,
  });

  it('sends a cleared field as null, so it can actually be cleared', () => {
    // Omitting it instead would make "remove this minimum" impossible: the backend patches
    // only the keys it is sent.
    expect(draftToPatch(draft({ moq: '' })).moq).toBeNull();
  });

  it('keeps zero as zero', () => {
    expect(draftToPatch(draft({ unit_cost: '0', currency: 'CNY' })).unit_cost).toBe(0);
  });

  it('rejects a price with no currency, and a zero price with no currency too', () => {
    expect(termsError(draft({ unit_cost: '10' }))).toMatch(/currency/i);
    expect(termsError(draft({ unit_cost: '0' }))).toMatch(/currency/i);
  });

  it('rejects an order multiple below one, which would round every buy to nothing', () => {
    expect(termsError(draft({ order_multiple: '0' }))).toMatch(/at least 1/i);
  });

  it('requires a lead time, because the column is NOT NULL', () => {
    expect(termsError(draft({ standard_lead_time_days: '' }))).toMatch(/lead time/i);
  });

  it('accepts a link with no price at all', () => {
    expect(termsError(draft())).toBeNull();
  });
});
