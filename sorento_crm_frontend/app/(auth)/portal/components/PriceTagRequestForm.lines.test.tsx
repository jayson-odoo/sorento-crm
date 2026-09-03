/**
 * D47 / AC-M.16: the lines table.
 *
 * One Add line button, one Item dropdown offering sets AND products, and a
 * payload whose shape did not move: `line_type` of `product` or `product_set`
 * with the matching id. The set row's Alternatives cell is disabled, which is
 * the capability the Set card this replaced never had.
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
  getRequest: vi.fn(),
  createRequest: vi.fn(),
  submitRequest: vi.fn(),
  approveRequest: vi.fn(),
  requestChanges: vi.fn(),
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

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    value: string[];
    disabled?: boolean;
    placeholder?: string;
  }) => (
    <select
      multiple
      aria-label="Alternatives"
      disabled={props.disabled}
      value={props.value}
      onChange={() => {}}
    />
  ),
}));

import {
  createRequest,
  lookupDebtors,
  lookupTagItems,
} from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';

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

async function addLine() {
  fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
}

describe('PriceTagRequestForm - one lines table, one item dropdown (D47)', () => {
  it('adds a row with one button and offers sets and products in one dropdown', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');

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
    await screen.findByLabelText('Debtor');
    fireEvent.change(screen.getByLabelText('Debtor'), {
      target: { value: 'ZZTD01' },
    });
    // The deadline starts empty since D48a, and Submit asks for it by name.
    fireEvent.change(screen.getByLabelText(/Needed by/), {
      target: { value: '2026-09-30' },
    });

    await addLine();
    await screen.findByText('ZZT Kitchen Sink');
    fireEvent.change(screen.getByLabelText('Search a set or product...'), {
      target: { value: 'product:prod-uuid-1' },
    });
    fireEvent.change(screen.getByLabelText('Quantity for line 1'), {
      target: { value: '2' },
    });

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

  it('a picked set posts line_type product_set and disables that row Alternatives', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    fireEvent.change(screen.getByLabelText('Debtor'), {
      target: { value: 'ZZTD01' },
    });
    // The deadline starts empty since D48a, and Submit asks for it by name.
    fireEvent.change(screen.getByLabelText(/Needed by/), {
      target: { value: '2026-09-30' },
    });

    await addLine();
    await screen.findByText('ZZT Bathroom Furniture Set');
    fireEvent.change(screen.getByLabelText('Search a set or product...'), {
      target: { value: 'product_set:set-uuid-1' },
    });

    expect(screen.getByLabelText('Alternatives')).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(createRequest).toHaveBeenCalled());
    const payload = (createRequest as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(payload.lines[0]).toMatchObject({
      line_type: 'product_set',
      product_set_id: 'set-uuid-1',
      product_id: null,
    });
    expect(payload.lines[0].alternatives).toEqual([]);
  });

  it('a product row keeps its Alternatives cell enabled', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');

    await addLine();
    await screen.findByText('ZZT Kitchen Sink');
    fireEvent.change(screen.getByLabelText('Search a set or product...'), {
      target: { value: 'product:prod-uuid-1' },
    });

    expect(screen.getByLabelText('Alternatives')).not.toBeDisabled();
  });

  it('removes a row without asking for a confirmation', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');

    await addLine();
    await screen.findByLabelText('Search a set or product...');
    fireEvent.click(screen.getByLabelText('Remove line 1'));

    await waitFor(() =>
      expect(screen.queryByLabelText('Search a set or product...')).toBeNull(),
    );
    expect(screen.getByText('No lines yet.')).toBeInTheDocument();
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
