/**
 * NPA-FROM-SI: the PRODUCT CODES header field shared by staff and portal.
 */
import React, { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { EMPTY_FORM, type FormState } from '@/lib/new-product-application-form';
import { NewProductApplicationProductCodes } from '@/components/common/NewProductApplicationProductCodes';

const CATALOGUE = [
  { value: 'p-1', label: 'A-1', description: 'Basin A' },
  { value: 'p-2', label: 'B-2', description: 'Cabinet B' },
];
const catalogue = async (q: string) =>
  CATALOGUE.filter((o) => o.label.toLowerCase().includes(q.toLowerCase()));

function Harness({
  initial = EMPTY_FORM,
  onState,
  ...rest
}: {
  initial?: FormState;
  onState?: (s: FormState) => void;
  readOnly?: boolean;
  reuse?: React.ComponentProps<typeof NewProductApplicationProductCodes>['reuse'];
}) {
  const [value, setValue] = useState(initial);
  return (
    <NewProductApplicationProductCodes
      value={value}
      onChange={(next) => {
        setValue(next);
        onState?.(next);
      }}
      products={catalogue}
      {...rest}
    />
  );
}

const picked = (...codes: [string, string][]): FormState => ({
  ...EMPTY_FORM,
  current_products: codes.map(([id, product_code]) => ({ id, product_code })),
});

describe('PRODUCT CODES field', () => {
  it('is a multi-select that keeps the picked order', async () => {
    const seen: FormState[] = [];
    render(<Harness onState={(s) => seen.push(s)} />);
    fireEvent.click(screen.getByRole('combobox', { name: 'Product codes' }));
    fireEvent.click(await screen.findByText('B-2'));
    await waitFor(() =>
      expect(seen.at(-1)!.current_products).toEqual([
        { id: 'p-2', product_code: 'B-2' },
      ]),
    );
    fireEvent.click(await screen.findByText('A-1'));
    await waitFor(() =>
      expect(seen.at(-1)!.current_products.map((p) => p.id)).toEqual(['p-2', 'p-1']),
    );
  });

  it('read-only shows plain comma text', () => {
    render(<Harness readOnly initial={picked(['p-1', 'A-1'], ['p-2', 'B-2'])} />);
    expect(screen.getByText('A-1, B-2')).toBeInTheDocument();
    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
  });

  it('read-only with nothing picked shows a dash', () => {
    render(<Harness readOnly />);
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('shows what the inquiry asked while nothing is picked, and hides it once picked', () => {
    const { unmount } = render(
      <Harness initial={{ ...EMPTY_FORM, inquiry_code_hint: 'XY-1 & XY-2' }} />,
    );
    expect(screen.getByText('Inquiry asked: "XY-1 & XY-2"')).toBeInTheDocument();
    unmount();
    render(
      <Harness
        initial={{ ...picked(['p-1', 'A-1']), inquiry_code_hint: 'XY-1' }}
      />,
    );
    expect(screen.queryByText(/Inquiry asked/)).toBeNull();
  });
});

describe('reuse suggestions', () => {
  const state = (suggestions: FormState['suggestions']): FormState => ({
    ...picked(['p-1', 'A-1']),
    suggestions,
    suggestions_for: 'p-1',
  });
  const sug = (over = {}) => ({
    product_id: 'p-9',
    product_code: 'A-1-69',
    product_name: null,
    is_active: true,
    description: 'no tap hole',
    created_at: '2026-11-03T02:00:00',
    ...over,
  });

  it('names the new code, application number, date and description (staff)', () => {
    render(
      <Harness
        readOnly
        initial={state([sug({ application_id: 'a-1', application_no: 'NPA-000123' })])}
      />,
    );
    expect(screen.getByTestId('npa-suggestions').textContent).toContain(
      'A code was already created from A-1: A-1-69 (NPA-000123, 03/11/2026, "no tap hole")',
    );
  });

  it('omits the application number on the portal shape', () => {
    render(<Harness readOnly initial={state([sug()])} />);
    const text = screen.getByTestId('npa-suggestions').textContent;
    expect(text).toContain('A-1-69 (03/11/2026, "no tap hole")');
    expect(text).not.toContain('NPA-');
  });

  it('lists at most three, in the order given', () => {
    const many = [1, 2, 3, 4].map((n) => sug({ product_id: `p-${n}`, product_code: `NEW-${n}` }));
    render(<Harness readOnly initial={state(many)} />);
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toContain('NEW-1');
  });

  it('shows nothing with no codes picked', () => {
    render(<Harness readOnly />);
    expect(screen.queryByTestId('npa-suggestions')).toBeNull();
  });

  it('asks again (debounced) when the pick differs from the loaded one', async () => {
    vi.useFakeTimers();
    try {
      const reuse = vi.fn().mockResolvedValue([sug({ product_code: 'B-2-69' })]);
      render(
        <Harness
          reuse={reuse}
          initial={{ ...picked(['p-2', 'B-2']), suggestions_for: '' }}
        />,
      );
      expect(reuse).not.toHaveBeenCalled();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });
      expect(reuse).toHaveBeenCalledWith(['p-2']);
      expect(screen.getByTestId('npa-suggestions').textContent).toContain('B-2-69');
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('a code with no product_code (NPA-FROM-SI)', () => {
  const ID = '3f9c2a64-7b1e-4d58-9a0c-5e2d8b7f1a10';
  const nameless = (): FormState => ({
    ...EMPTY_FORM,
    current_products: [{ id: ID, product_code: '' }],
  });

  it('read-only shows no raw id', () => {
    render(<Harness initial={nameless()} readOnly />);
    expect(document.body.textContent ?? '').not.toContain(ID);
  });

  it('the picker chip shows no raw id', () => {
    render(<Harness initial={nameless()} />);
    expect(document.body.textContent ?? '').not.toContain(ID);
  });
});
