/**
 * M5-06 - the "Line items" table renders on DataGrid instead of a raw
 * `<Table>`. This is the inline-editing case the M5 run 3 brief called out as
 * a possible blocker: each cell is a react-hook-form field bound through
 * useFieldArray. It is not a blocker - DataGrid renders the same
 * FormField/Input tree the raw table did, keyed the same way (row id, column
 * id), so React's reconciliation preserves the input's identity across
 * keystrokes exactly like the hand-rolled table did.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
import { useForm, useFieldArray, type UseFormReturn } from 'react-hook-form';

import { Form } from '@/components/ui/form';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/purchase-requests/pr-1',
}));

vi.mock('@/hooks/useCurrencyFormat', () => ({
  useCurrencyFormat: () => 'RM {value}',
}));
vi.mock('@/components/common/LookupBoundField', () => ({
  __esModule: true,
  default: () => null,
}));
vi.mock(
  '@/app/(protected)/master-data-management/shared/components/RequestorContactSelect',
  () => ({ RequestorContactSelect: () => null }),
);
vi.mock('./PurchaseRequestSignoffFooter', () => ({
  PurchaseRequestSignoffFooter: () => null,
}));

import { PurchaseRequestDocumentEditCard } from './PurchaseRequestDocumentEditCard';
import type { PurchaseRequestSchemaType } from '../forms/purchase-request-schema';
import type { PurchaseRequest } from '../types/purchaseRequest.types';

function request(over: Partial<PurchaseRequest> = {}): PurchaseRequest {
  return {
    id: 'pr-1',
    request_type: 'purchase_request',
    request_number: 'PR26-0332',
    revision_no: 0,
    lines: [],
    ...over,
  } as PurchaseRequest;
}

/**
 * Renders with a REAL useFieldArray, the way PurchaseRequestForm does -
 * INCLUDING the parent's own `form.watch('products')` (PurchaseRequestForm.tsx,
 * `sponsorshipLineGrandTotal`), so the Harness re-renders on every keystroke
 * exactly as the real parent does. Without this the test only ever exercised a
 * Harness that stayed still while typing, which cannot tell a memo keyed on
 * `fields.length` apart from one that is not - both look identical to a parent
 * that never re-renders.
 */
function Harness({ record }: { record: PurchaseRequest }) {
  const form = useForm<PurchaseRequestSchemaType>({
    defaultValues: {
      request_type: record.request_type,
      request_number: record.request_number ?? null,
      products: [
        { item_code: 'ITEM-A', quantity: 4, remark: 'First', unit_price: null, total: null },
        { item_code: 'ITEM-B', quantity: 2, remark: 'Second', unit_price: null, total: null },
      ],
    } as unknown as PurchaseRequestSchemaType,
  });
  const { fields, append, remove } = useFieldArray({ control: form.control, name: 'products' });
  form.watch('products');
  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(() => {})}>
        <PurchaseRequestDocumentEditCard
          form={form}
          request={record}
          isSponsorship={record.request_type === 'sponsorship_form'}
          showTypeSelect={false}
          fields={fields}
          append={append}
          remove={remove}
          sponsorshipLineGrandTotal={0}
        />
      </form>
    </Form>
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('PurchaseRequestDocumentEditCard - line items DataGrid', () => {
  it('renders the column headers and a real cell value for each line', () => {
    render(<Harness record={request()} />);

    expect(screen.getByText('Item Code')).toBeInTheDocument();
    expect(screen.getByText('Qty')).toBeInTheDocument();
    expect(screen.getByText('Remark')).toBeInTheDocument();

    expect(screen.getByDisplayValue('ITEM-A')).toBeInTheDocument();
    expect(screen.getByDisplayValue('ITEM-B')).toBeInTheDocument();
  });

  it('keeps focus on the item-code input while typing (D2/M5-06 inline-editing check)', () => {
    render(<Harness record={request()} />);

    const input = screen.getByDisplayValue('ITEM-A') as HTMLInputElement;
    input.focus();
    fireEvent.change(input, { target: { value: 'ITEM-A2' } });

    expect(document.activeElement).toBe(input);
    expect(input.value).toBe('ITEM-A2');
  });

  it('SF-5: typing into row 1 then appending a row keeps row 1\'s value AND input identity', () => {
    // The bug this guards: `fields.length` sat in the columns `useMemo` deps, so
    // an append recreated every cell type and remounted every input - values
    // survived (react-hook-form owns them) but identity did not.
    const Wrapper = () => {
      const form = useForm<PurchaseRequestSchemaType>({
        defaultValues: {
          request_type: 'purchase_request',
          request_number: 'PR26-0332',
          products: [{ item_code: 'ITEM-A', quantity: 4, remark: null, unit_price: null, total: null }],
        } as unknown as PurchaseRequestSchemaType,
      });
      const { fields, append, remove } = useFieldArray({ control: form.control, name: 'products' });
      form.watch('products');
      return (
        <Form {...form}>
          <form onSubmit={form.handleSubmit(() => {})}>
            <PurchaseRequestDocumentEditCard
              form={form}
              request={request()}
              isSponsorship={false}
              showTypeSelect={false}
              fields={fields}
              append={append}
              remove={remove}
              sponsorshipLineGrandTotal={0}
            />
          </form>
        </Form>
      );
    };
    render(<Wrapper />);

    const first = screen.getByDisplayValue('ITEM-A') as HTMLInputElement;
    fireEvent.change(first, { target: { value: 'ITEM-A2' } });
    expect(first.value).toBe('ITEM-A2');

    fireEvent.click(screen.getByRole('button', { name: /Add row/i }));

    const inputsAfter = screen.getAllByPlaceholderText('Item code');
    expect(inputsAfter[0]).toBe(first);
    expect((inputsAfter[0] as HTMLInputElement).value).toBe('ITEM-A2');
  });

  it('shows the U/P and Total columns on a sponsorship form, not on a purchase request', () => {
    const { rerender } = render(<Harness record={request()} />);
    expect(screen.queryByText('U/P *')).not.toBeInTheDocument();
    expect(screen.queryByText('Total')).not.toBeInTheDocument();

    rerender(<Harness record={request({ request_type: 'sponsorship_form' })} />);
    // #1227: the asterisk marks unit price as required - sponsorship lines only.
    expect(screen.getByText('U/P *')).toBeInTheDocument();
    expect(screen.getByText('Total')).toBeInTheDocument();
  });

  it('the required-price inline message renders full and unclipped in the edit DataGrid cell (#1232 round 2 blocking 1)', () => {
    let formRef: UseFormReturn<PurchaseRequestSchemaType> | undefined;
    const Wrapper = () => {
      const form = useForm<PurchaseRequestSchemaType>({
        defaultValues: {
          request_type: 'sponsorship_form',
          request_number: 'PR26-0332',
          products: [{ item_code: 'ITEM-A', quantity: 4, remark: null, unit_price: null, total: null }],
        } as unknown as PurchaseRequestSchemaType,
      });
      formRef = form;
      const { fields, append, remove } = useFieldArray({ control: form.control, name: 'products' });
      form.watch('products');
      return (
        <Form {...form}>
          <form onSubmit={form.handleSubmit(() => {})}>
            <PurchaseRequestDocumentEditCard
              form={form}
              request={request({ request_type: 'sponsorship_form' })}
              isSponsorship
              showTypeSelect={false}
              fields={fields}
              append={append}
              remove={remove}
              sponsorshipLineGrandTotal={0}
            />
          </form>
        </Form>
      );
    };
    render(<Wrapper />);

    act(() => {
      formRef!.setError('products.0.unit_price', { type: 'custom', message: 'Unit price is required.' });
    });

    const message = screen.getByText('Unit price is required.');
    expect(message).toBeInTheDocument();
    // Round 2 blocking 1: the U/P column (size 120) sits in a resizable DataGrid,
    // whose cell carries a `truncate` class - `overflow: hidden` plus an inherited
    // `white-space: nowrap` that clipped this sentence to "Unit price is requir" in
    // the committed edit screenshots. The FormMessage must opt back into wrapping.
    expect(message.textContent).toBe('Unit price is required.');
    expect(message.className).toContain('whitespace-normal');
  });
});
