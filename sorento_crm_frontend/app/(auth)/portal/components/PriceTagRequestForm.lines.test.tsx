/**
 * D47 / AC-M.16: the lines table.
 *
 * One Add line button, one Item dropdown offering sets AND products, and a
 * payload whose shape did not move: `line_type` of `product` or `product_set`
 * with the matching id. r7 (PLAN-price-tag-r7-request-ux D3/AC-S1-3) removed
 * the Alternatives column from the table entirely - `alternatives` stays in
 * the payload shape (so an existing row still round-trips) but there is no
 * longer a control to edit it.
 *
 * Also D46a: an EMPTY debtor lookup explains itself; a FAILED one does not.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));
const toastError = toasts.error;

vi.mock('../lib/price-tag-request-service', () => ({
  lookupDebtors: vi.fn(),
  lookupPromotions: vi.fn(async () => []),
  lookupTagItems: vi.fn(),
  lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
  getRequest: vi.fn(),
  createRequest: vi.fn(),
  submitRequest: vi.fn(),
  approveRequest: vi.fn(),
  requestChanges: vi.fn(),
  listReviewComments: vi.fn(async () => []),
  collectRequest: vi.fn(),
}));

/**
 * Stubbed as a native select so a pick is one `fireEvent.change`. The real
 * component is a Radix popover whose options only exist while it is open, which
 * tests the popover rather than the payload.
 */
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
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
    return (
      <select
        aria-label={props.id === 'debtor' ? 'Debtor' : (props.placeholder ?? '')}
        value={props.value}
        onChange={(e) => {
          props.onChange(e.target.value);
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

import {
  createRequest,
  lookupDebtors,
  lookupTagItems,
} from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';
import { selectOption } from '@/test-utils';

const DEBTORS = [{ code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' }];

const ITEMS = [
  {
    kind: 'product_set' as const,
    id: 'set-uuid-1',
    code: 'ZZTSET-1',
    name: 'ZZT Bathroom Furniture Set',
  },
  {
    kind: 'product' as const,
    id: 'prod-uuid-1',
    code: 'CBF-1234',
    name: 'ZZT Kitchen Sink',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  (lookupDebtors as ReturnType<typeof vi.fn>).mockResolvedValue(DEBTORS);
  (lookupTagItems as ReturnType<typeof vi.fn>).mockResolvedValue(ITEMS);
  (createRequest as ReturnType<typeof vi.fn>).mockResolvedValue({ id: 'req-1' });
});

// The lines table (and its "Add line" button) lives inside the "Sales Order
// & Lines" section (D-P1), which is collapsed until a customer is picked
// (AC-P3) or opened by hand - Radix's Collapsible unmounts its content while
// closed, so a test that never picks a customer has to open it itself.
function openSalesOrderSection() {
  fireEvent.click(screen.getByRole('button', { name: /Sales Order & Lines/ }));
}

async function addLine() {
  fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
}

/**
 * r9 D7: `Printing` has no default and Submit refuses without it, so every
 * test that expects a POST has to answer it first. The control lives in
 * "Additional Information", which is collapsed until a price mode is chosen.
 */
async function pickPrinting() {
  if (!screen.queryByRole('radio', { name: 'Office prints' })) {
    fireEvent.click(
      screen.getByRole('button', { name: /Additional Information/ }),
    );
  }
  fireEvent.click(await screen.findByRole('radio', { name: 'Office prints' }));
}

describe('PriceTagRequestForm - one lines table, one item dropdown (D47)', () => {
  it('adds a row with one button and offers sets and products in one dropdown', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    openSalesOrderSection();

    // The two Add buttons are gone: there is exactly one.
    expect(screen.queryByRole('button', { name: /^Product$/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Set$/ })).toBeNull();

    await addLine();
    const item = await screen.findByLabelText('Search a set or product...');
    await waitFor(() =>
      expect(
        screen.getByText('ZZT Bathroom Furniture Set'),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText('ZZT Kitchen Sink')).toBeInTheDocument();
    expect(item).toBeInTheDocument();
  });

  it('a picked product posts line_type product with the product id', async () => {
    render(<PriceTagRequestForm />);
    // Need by is optional since D-P2b - Customer + one line is the whole
    // requirement (AC-P10); picking the customer auto-opens Sales Order &
    // Lines (AC-P3).
    await selectOption('Debtor', 'ZZTD01');

    await addLine();
    await selectOption('Search a set or product...', 'product:prod-uuid-1');
    fireEvent.change(screen.getByLabelText('Quantity for line 1'), {
      target: { value: '2' },
    });

    await pickPrinting();
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));

    await waitFor(() => expect(createRequest).toHaveBeenCalled());
    const payload = (createRequest as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(payload.lines).toHaveLength(1);
    expect(payload.lines[0]).toMatchObject({
      line_type: 'product',
      product_id: 'prod-uuid-1',
      product_set_id: null,
      quantity: 2,
    });
  });

  it('a picked set posts line_type product_set with no product id', async () => {
    render(<PriceTagRequestForm />);
    // Need by is optional since D-P2b - see the note above.
    await selectOption('Debtor', 'ZZTD01');

    await addLine();
    await selectOption('Search a set or product...', 'product_set:set-uuid-1');

    await pickPrinting();
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(createRequest).toHaveBeenCalled());
    const payload = (createRequest as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(payload.lines[0]).toMatchObject({
      line_type: 'product_set',
      product_set_id: 'set-uuid-1',
      product_id: null,
    });
    // `alternatives` is GONE (S2, AC-S2-8) - the column is dropped and the
    // payload never carries it again. What replaces it is `parts`: a set line
    // has none (parts are a combo fact on a product line), so it posts empty
    // rather than absent.
    expect(payload.lines[0].alternatives).toBeUndefined();
    expect(payload.lines[0].parts).toEqual([]);
  });

  it('a set row has no Alternatives column (D3/AC-S1-3)', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    openSalesOrderSection();

    await addLine();
    await selectOption('Search a set or product...', 'product_set:set-uuid-1');

    expect(screen.queryByLabelText('Alternatives')).toBeNull();
    expect(screen.queryByText('Alternatives')).toBeNull();
  });

  it('a product row has no Alternatives column either', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    openSalesOrderSection();

    await addLine();
    await selectOption('Search a set or product...', 'product:prod-uuid-1');

    expect(screen.queryByLabelText('Alternatives')).toBeNull();
    expect(screen.queryByText('Alternatives')).toBeNull();
  });

  it('removes a row without asking for a confirmation', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    openSalesOrderSection();

    await addLine();
    await screen.findByLabelText('Search a set or product...');
    fireEvent.click(screen.getByLabelText('Remove line 1'));

    await waitFor(() =>
      expect(screen.queryByLabelText('Search a set or product...')).toBeNull(),
    );
    expect(screen.getByText('No lines yet.')).toBeInTheDocument();
  });
});

describe('PriceTagRequestForm - no line reorder arrows (R3-6, AC-R12)', () => {
  it('renders no up/down move buttons on a line', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    openSalesOrderSection();

    await addLine();
    await screen.findByLabelText('Search a set or product...');

    expect(screen.queryByLabelText(/Move line 1 up/)).toBeNull();
    expect(screen.queryByLabelText(/Move line 1 down/)).toBeNull();
    expect(screen.queryByTitle('Move up')).toBeNull();
    expect(screen.queryByTitle('Move down')).toBeNull();
  });
});

describe('PriceTagRequestForm - duplicate product refused inline (R3-7, AC-R12)', () => {
  it('picking a product already on the request shows an inline message and does not add a line', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    openSalesOrderSection();

    await addLine();
    await selectOption('Search a set or product...', 'product:prod-uuid-1');

    await addLine();
    const pickers = screen.getAllByLabelText('Search a set or product...');
    const secondPicker = pickers[1] as HTMLSelectElement;
    // The mocked SearchableSelect resolves its options asynchronously
    // (fetchOptions), so the second instance needs the same wait
    // `selectOption` (test-utils) gives the first - firing the change before
    // it resolves finds no matching option and the handler no-ops.
    await waitFor(() =>
      expect(Array.from(secondPicker.options).map((o) => o.value)).toContain(
        'product:prod-uuid-1',
      ),
    );
    fireEvent.change(secondPicker, { target: { value: 'product:prod-uuid-1' } });

    expect(
      await screen.findByText(/already on this request/i),
    ).toBeInTheDocument();
    // The second row stays an empty, unpicked line - the duplicate is
    // refused before it ever becomes a second real line for the product.
    expect(secondPicker).toHaveValue('');
  });
});

describe('PriceTagRequestForm - the debtor dropdown explains itself (D46a)', () => {
  it('shows the not-linked notice when the lookup answers with nothing', async () => {
    (lookupDebtors as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    render(<PriceTagRequestForm />);

    const notice = await screen.findByTestId('no-debtors-notice');
    expect(notice).toHaveTextContent('not linked to a sales agent yet');
    expect(screen.queryByLabelText('Debtor')).toBeNull();
    expect(toastError).not.toHaveBeenCalled();
  });

  it('keeps the toast, and no notice, when the lookup FAILS', async () => {
    (lookupDebtors as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('boom'),
    );
    render(<PriceTagRequestForm />);

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(screen.queryByTestId('no-debtors-notice')).toBeNull();
    expect(screen.getByLabelText('Debtor')).toBeInTheDocument();
  });
});
