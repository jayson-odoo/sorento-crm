/**
 * NEW-PRODUCT-APP v5 (AC-NPA-80): the products are ONE line table, one row per product, shared by
 * staff and portal. Assumed props (the coder matches them):
 *   lines: DraftLine[], onChange(next), brands: LookupFetcher, errors?: Record<string,string>,
 *   readOnly?: boolean,
 *   showCost?: boolean        (adds the Cost (MYR) column),
 *   costEditable?: boolean    (with showCost: a per-row input "Cost for product N"; else text),
 *   renderOpenedAs?: (line: DraftLine, index: number) => ReactNode  (adds the "Opened as" column).
 * Row controls: "Add row" button, per-row remove button named "Remove row N".
 */
import React, { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { blankLine, type DraftLine } from '@/lib/new-product-application-form';
import { NewProductApplicationLines } from '@/components/common/NewProductApplicationLines';

type Extra = Partial<
  Pick<
    React.ComponentProps<typeof NewProductApplicationLines>,
    'readOnly' | 'showCost' | 'costEditable' | 'renderOpenedAs' | 'reuse' | 'products'
  >
>;

const CATALOGUE = [
  { value: 'p-1', label: 'A-1', description: 'Basin A' },
  { value: 'p-2', label: 'B-2', description: 'Cabinet B' },
];
const catalogue = async (q: string) =>
  CATALOGUE.filter((o) => o.label.toLowerCase().includes(q.toLowerCase()));

function Harness({
  initial,
  onState,
  ...extra
}: { initial: DraftLine[]; onState?: (l: DraftLine[]) => void } & Extra) {
  const [lines, setLines] = useState(initial);
  return (
    <NewProductApplicationLines
      lines={lines}
      onChange={(next: DraftLine[]) => {
        setLines(next);
        onState?.(next);
      }}
      brands={async () => []}
      products={catalogue}
      {...extra}
    />
  );
}

const two = () => [blankLine(), blankLine()];

describe('the line table', () => {
  it('has the paper columns in order, Product type marked required, and no card or image controls', () => {
    render(<Harness initial={two()} />);
    const names = screen
      .getAllByRole('columnheader')
      .map((h) => (h.textContent ?? '').trim())
      .filter(Boolean);
    const want = [
      /^No\.?$/i,
      /^Product code/i,
      /^Product type/i,
      /^Dimension/i,
      /^Material/i,
      /^Thickness/i,
      /^Packing/i,
      /^Brand/i,
      /^Qty/i,
    ];
    let at = -1;
    for (const re of want) {
      const i = names.findIndex((n, idx) => idx > at && re.test(n));
      expect(i, `column ${re} after ${at} in ${names.join(' | ')}`).toBeGreaterThan(at);
      at = i;
    }
    expect(
      names.find((n) => /^Product type/i.test(n)),
    ).toMatch(/\*/);
    expect(screen.queryByText(/product \d+ of \d+/i)).toBeNull();
    expect(screen.queryByLabelText(/add image/i)).toBeNull();
    expect(screen.queryByText(/copy from the inquiry/i)).toBeNull();
    expect(screen.queryByLabelText(/item group|base uom|selling|supplier/i)).toBeNull();
  });

  it('Add row adds a row and a per-row remove control removes that row', () => {
    render(<Harness initial={[blankLine()]} />);
    expect(screen.getAllByLabelText('Product type')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: /add row/i }));
    expect(screen.getAllByLabelText('Product type')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: /^remove row 1$/i }));
    expect(screen.getAllByLabelText('Product type')).toHaveLength(1);
  });

  it('types into the cells of one row only', () => {
    const seen: DraftLine[][] = [];
    render(<Harness initial={two()} onState={(l) => seen.push(l)} />);
    fireEvent.change(screen.getAllByLabelText('Product type')[1], {
      target: { value: 'Example sink' },
    });
    fireEvent.change(screen.getAllByLabelText('Dimension')[1], {
      target: { value: '600x400' },
    });
    fireEvent.change(screen.getAllByLabelText('Qty')[1], {
      target: { value: '55' },
    });
    const last = seen.at(-1)!;
    expect(last[1]).toMatchObject({
      description: 'Example sink',
      dimension: '600x400',
      expected_qty: '55',
    });
    expect(last[0].description).toBe('');
  });

  it('read-only renders plain text: no inputs, no Add row, no remove control, empty as a dash', () => {
    const row = {
      ...blankLine(),
      id: 'l-1',
      current_products: [
        { id: 'p-1', product_code: 'XY-1' },
        { id: 'p-2', product_code: 'XY-2' },
      ],
      description: 'Example sink',
      expected_qty: '55',
    };
    render(<Harness initial={[row]} readOnly />);
    expect(screen.queryAllByRole('textbox')).toHaveLength(0);
    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
    expect(screen.queryAllByRole('spinbutton')).toHaveLength(0);
    expect(screen.getByText('XY-1, XY-2')).toBeInTheDocument();
    expect(screen.getByText('Example sink')).toBeInTheDocument();
    expect(screen.getByText('55')).toBeInTheDocument();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /add row/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^remove row/i })).toBeNull();
  });
});

describe('Cost (MYR) column', () => {
  const rows = () => [
    { ...blankLine(), id: 'l-1', cost_price: '' },
    { ...blankLine(), id: 'l-2', cost_price: '' },
  ];

  it('is absent unless asked for', () => {
    render(<Harness initial={rows()} />);
    expect(screen.queryByRole('columnheader', { name: /cost/i })).toBeNull();
    expect(screen.queryByLabelText(/^cost/i)).toBeNull();
  });

  it('is read-only text when not editable', () => {
    render(
      <Harness
        initial={[{ ...blankLine(), id: 'l-1', cost_price: '12.50' }]}
        showCost
      />,
    );
    expect(screen.getByRole('columnheader', { name: /cost \(myr\)/i })).toBeInTheDocument();
    expect(screen.getByText(/12\.50/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^cost/i)).toBeNull();
  });

  it('has one uniquely named input per row when editable', () => {
    const seen: DraftLine[][] = [];
    render(
      <Harness initial={rows()} showCost costEditable onState={(l) => seen.push(l)} />,
    );
    expect(screen.getByLabelText('Cost for product 1')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Cost for product 2'), {
      target: { value: '9.90' },
    });
    expect(seen.at(-1)![1].cost_price).toBe('9.90');
    expect(seen.at(-1)![0].cost_price).toBe('');
  });
});

describe('Opened as column', () => {
  it('shows what the host renders for each row', () => {
    render(
      <Harness
        initial={[{ ...blankLine(), id: 'l-1' }, { ...blankLine(), id: 'l-2' }]}
        readOnly
        renderOpenedAs={(_l: DraftLine, i: number) => <span>opened-slot-{i + 1}</span>}
      />,
    );
    expect(screen.getByRole('columnheader', { name: /opened as/i })).toBeInTheDocument();
    const rows = screen.getAllByRole('row');
    expect(within(rows[1]).getByText('opened-slot-1')).toBeInTheDocument();
    expect(within(rows[2]).getByText('opened-slot-2')).toBeInTheDocument();
  });
});

describe('Product code cell (current codes)', () => {
  it('is a multi-select that sends the picked ids in picked order', async () => {
    const seen: DraftLine[][] = [];
    render(<Harness initial={[blankLine()]} onState={(l) => seen.push(l)} />);
    expect(screen.queryAllByRole('textbox', { name: 'Product code' })).toHaveLength(0);

    const open = () =>
      fireEvent.click(screen.getByRole('combobox', { name: 'Product code' }));
    open();
    fireEvent.click(await screen.findByText('B-2'));
    await waitFor(() =>
      expect(seen.at(-1)![0].current_products).toEqual([
        { id: 'p-2', product_code: 'B-2' },
      ]),
    );
    fireEvent.click(await screen.findByText('A-1'));
    await waitFor(() =>
      expect(seen.at(-1)![0].current_products.map((p) => p.id)).toEqual([
        'p-2',
        'p-1',
      ]),
    );
  });

  it('read-only shows the codes as plain comma text, a dash when none', () => {
    render(
      <Harness
        readOnly
        initial={[
          {
            ...blankLine(),
            id: 'l-1',
            current_products: [
              { id: 'p-1', product_code: 'A-1' },
              { id: 'p-2', product_code: 'B-2' },
            ],
          },
          { ...blankLine(), id: 'l-2' },
        ]}
      />,
    );
    expect(screen.getByText('A-1, B-2')).toBeInTheDocument();
    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
  });

  it('shows what the inquiry asked, read-only, while no code is picked', () => {
    render(
      <Harness
        initial={[{ ...blankLine(), inquiry_code_hint: 'XY-1 & XY-2' }]}
      />,
    );
    expect(screen.getByText('Inquiry asked: "XY-1 & XY-2"')).toBeInTheDocument();
  });

  it('hides the hint once a code is picked', () => {
    render(
      <Harness
        initial={[
          {
            ...blankLine(),
            inquiry_code_hint: 'XY-1',
            current_products: [{ id: 'p-1', product_code: 'A-1' }],
          },
        ]}
      />,
    );
    expect(screen.queryByText(/Inquiry asked/)).toBeNull();
  });
});

describe('Reuse suggestion row', () => {
  const line = (over: Partial<DraftLine> = {}): DraftLine => ({
    ...blankLine(),
    id: 'l-1',
    current_products: [{ id: 'p-1', product_code: 'A-1' }],
    suggestions_for: 'p-1',
    ...over,
  });

  it('names the new code, application number, date and description (staff)', () => {
    render(
      <Harness
        readOnly
        initial={[
          line({
            suggestions: [
              {
                product_id: 'p-9',
                product_code: 'A-1-69',
                product_name: 'Basin',
                is_active: true,
                description: 'no tap hole',
                created_at: '2026-11-03T02:00:00',
                application_id: 'a-1',
                application_no: 'NPA-000123',
              },
            ],
          }),
        ]}
      />,
    );
    const row = screen.getByTestId('npa-line-suggestions');
    expect(row.textContent).toContain(
      'A code was already created from A-1: A-1-69 (NPA-000123, 03/11/2026, "no tap hole")',
    );
  });

  it('omits the application number when the portal shape carries none', () => {
    render(
      <Harness
        readOnly
        initial={[
          line({
            suggestions: [
              {
                product_id: 'p-9',
                product_code: 'A-1-69',
                product_name: null,
                is_active: true,
                description: 'no tap hole',
                created_at: '2026-11-03T02:00:00',
              },
            ],
          }),
        ]}
      />,
    );
    const text = screen.getByTestId('npa-line-suggestions').textContent;
    expect(text).toContain('A-1-69 (03/11/2026, "no tap hole")');
    expect(text).not.toContain('NPA-');
  });

  it('lists at most three, in the order given', () => {
    const many = [1, 2, 3, 4].map((n) => ({
      product_id: `p-${n}`,
      product_code: `NEW-${n}`,
      product_name: null,
      is_active: true,
      description: null,
      created_at: null,
    }));
    render(<Harness readOnly initial={[line({ suggestions: many })]} />);
    const items = within(screen.getByTestId('npa-line-suggestions')).getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toContain('NEW-1');
  });

  it('shows nothing for a line with no current codes', () => {
    render(<Harness readOnly initial={[{ ...blankLine(), id: 'l-1' }]} />);
    expect(screen.queryByTestId('npa-line-suggestions')).toBeNull();
  });

  it('asks again (debounced) when the picked codes differ from the loaded ones', async () => {
    vi.useFakeTimers();
    try {
      const reuse = vi.fn().mockResolvedValue([
        {
          product_id: 'p-9',
          product_code: 'B-2-69',
          product_name: null,
          is_active: true,
          description: 'other change',
          created_at: null,
        },
      ]);
      render(
        <Harness
          reuse={reuse}
          initial={[
            {
              ...blankLine(),
              id: 'l-1',
              current_products: [{ id: 'p-2', product_code: 'B-2' }],
              suggestions_for: '',
            },
          ]}
        />,
      );
      expect(reuse).not.toHaveBeenCalled();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });
      expect(reuse).toHaveBeenCalledWith(['p-2']);
      expect(screen.getByTestId('npa-line-suggestions').textContent).toContain(
        'B-2-69',
      );
    } finally {
      vi.useRealTimers();
    }
  });
});
