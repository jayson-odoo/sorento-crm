/**
 * The lines of a sales order as a spreadsheet, and the guard that keeps it honest.
 *
 * The binding rule is that read and edit present the SAME structure: the columns the read
 * DataGrid declares and the columns this editor declares have to be the same headers in the
 * same order, or every edit starts with the user re-finding the cell they came to change. Two
 * column lists cannot be one list (a `ColumnDef` and an `InlineLineColumn` are different
 * shapes), so the agreement is asserted here instead of hoped for.
 *
 * The rest of the file pins the behaviour of an edit session: nothing is written, every change
 * is reported upwards, and a removal is staged rather than done.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render as rtlRender, screen, fireEvent, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  ProjectSalesOrderFinding,
  ProjectSalesOrderLine,
  StagedSalesOrderLine,
} from '../../_shared/types/projectSalesOrder.types';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query', () => ({
  useUOMSelectQuery: () => ({
    data: [
      { id: 'u1', uom_code: 'UNIT', uom_name: 'Unit' },
      { id: 'u2', uom_code: 'SET', uom_name: 'Set' },
    ],
    isLoading: false,
  }),
}));

vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForVariantSelect: vi.fn(async () => [
    { id: 'p9', product_code: 'SRT382-6', product_name: 'Floor grating' },
  ]),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options,
    placeholder,
    selectedOption,
  }: {
    id?: string;
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    selectedOption?: { value: string; label: string };
  }) => (
    <select
      id={id}
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? (selectedOption ? [selectedOption] : [])).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { SalesOrderLinesEditor } from './SalesOrderLinesEditor';
import { SalesOrderLinesTable } from './SalesOrderLinesTable';

const LINES: ProjectSalesOrderLine[] = [
  {
    id: 'l1',
    line_no: 1,
    product_id: 'p1',
    product_code: 'CB6633',
    description: 'CABANA S/STEEL FLOOR GRATING 6"',
    qty: '600',
    uom: 'UNIT',
    unit_price: '11.16000',
    amount: '6696.00',
    delivery_date: '2026-07-01',
    phase_label: 'Level 2 & 7',
    explosion_source: 'none',
    source_po_line_no: 1,
    stock_location: 'BRW-BB',
  },
  {
    id: 'l2',
    line_no: 2,
    product_id: 'p2',
    product_code: 'SRT382-6',
    description: 'SORENTO STAINLESS STEEL FLOOR GRATING 6" x 6"',
    qty: '135',
    uom: 'UNIT',
    unit_price: '13.77000',
    amount: '1858.95',
    delivery_date: '2026-07-01',
    phase_label: 'Level 2 & 7',
    explosion_source: 'none',
    source_po_line_no: 2,
    stock_location: 'BRW-BB',
  },
];

const HARD: ProjectSalesOrderFinding = {
  id: 'f1',
  severity: 'hard',
  code: 'line_arithmetic',
  detail: 'Line 1: 600 x 11.16 is 6,696.00 but the PO says 6,690.00.',
  line_id: 'l1',
  line_no: 1,
};

function staged(lines: ProjectSalesOrderLine[]): StagedSalesOrderLine[] {
  return lines.map((line) => ({
    id: line.id,
    key: line.id,
    line,
    draft: {
      product_id: line.product_id ?? '',
      description: line.description ?? '',
      qty: line.qty,
      uom: line.uom ?? '',
      unit_price: line.unit_price,
      delivery_date: line.delivery_date ?? '',
      stock_location: line.stock_location ?? '',
    },
    removed: false,
  }));
}

function editing(overrides: Record<string, unknown> = {}) {
  return {
    staged: staged(LINES),
    seed: vi.fn(),
    stage: vi.fn(),
    toggleRemoved: vi.fn(),
    ...overrides,
  };
}

/**
 * `InlineLineTable` mounts the shared `ConfirmDeleteDialog`, which reads react-query's client
 * even while closed, so every render needs a provider.
 */
function render(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => vi.clearAllMocks());

describe('the read and the edit declare the same columns', () => {
  it('names the same headers in the same order', () => {
    const read = render(<SalesOrderLinesTable lines={LINES} />);
    const readHeaders = Array.from(
      read.container.querySelectorAll('thead th'),
    ).map((cell) => (cell.textContent ?? '').trim());
    read.unmount();

    const write = render(<SalesOrderLinesEditor lines={LINES} editing={editing()} />);
    const writeHeaders = Array.from(write.container.querySelectorAll('thead th'))
      .map((cell) => (cell.textContent ?? '').trim())
      // The editor adds one trailing column for the row's own remove button, which the read
      // view has no counterpart for and deliberately does not draw.
      .filter((text) => text !== '' && text !== 'Row actions');

    expect(writeHeaders).toEqual(readHeaders.filter((text) => text !== ''));
  });
});

describe('SalesOrderLinesEditor, reading', () => {
  it('draws every line as text with nothing to type into', () => {
    render(<SalesOrderLinesEditor lines={LINES} />);

    expect(screen.getByText('CABANA S/STEEL FLOOR GRATING 6"')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add a line/ })).not.toBeInTheDocument();
  });

  it('states the absence when the draft has no lines', () => {
    render(<SalesOrderLinesEditor lines={[]} />);

    expect(screen.getByText(/This draft has no lines/)).toBeInTheDocument();
  });

  it('seeds the session from the server rows the first time it opens', () => {
    const session = editing({ staged: null });

    render(<SalesOrderLinesEditor lines={LINES} editing={session} />);

    expect(session.seed).toHaveBeenCalledTimes(1);
    const seeded = session.seed.mock.calls[0][0] as StagedSalesOrderLine[];
    expect(seeded.map((line) => line.id)).toEqual(['l1', 'l2']);
    expect(seeded[0].draft.qty).toBe('600');
  });
});

describe('SalesOrderLinesEditor, editing', () => {
  it('puts an input where the value was, per line', () => {
    render(<SalesOrderLinesEditor lines={LINES} editing={editing()} />);

    expect(
      screen.getByRole('textbox', { name: /Description on CB6633/ }),
    ).toHaveValue('CABANA S/STEEL FLOOR GRATING 6"');
    expect(screen.getByRole('textbox', { name: /Qty on CB6633/ })).toHaveValue('600');
  });

  it('reports every change upwards instead of writing it', () => {
    const session = editing();
    render(<SalesOrderLinesEditor lines={LINES} editing={session} />);

    fireEvent.change(screen.getByRole('textbox', { name: /Qty on CB6633/ }), {
      target: { value: '601' },
    });

    expect(session.stage).toHaveBeenCalled();
    const reported = session.stage.mock.calls.at(-1)?.[0] as StagedSalesOrderLine[];
    expect(reported[0].draft.qty).toBe('601');
    expect(reported[0].id).toBe('l1');
  });

  it('recomputes the amount from the live draft, so the footer cannot lag the cells', () => {
    render(<SalesOrderLinesEditor lines={LINES} editing={editing()} />);

    // 600 x 11.16 + 135 x 13.77
    expect(screen.getByText('RM 8,554.95')).toBeInTheDocument();
  });

  it('adds an empty row at the bottom without saving anything', () => {
    const session = editing();
    render(<SalesOrderLinesEditor lines={LINES} editing={session} />);

    fireEvent.click(screen.getByRole('button', { name: /Add a line/ }));

    const reported = session.stage.mock.calls.at(-1)?.[0] as StagedSalesOrderLine[];
    expect(reported).toHaveLength(3);
    expect(reported[2].id).toBeNull();
  });

  it('stages a removal rather than asking to confirm it', () => {
    const session = editing();
    render(<SalesOrderLinesEditor lines={LINES} editing={session} />);

    fireEvent.click(screen.getByRole('button', { name: /Remove CB6633/ }));

    expect(session.toggleRemoved).toHaveBeenCalledWith('l1');
    // No dialog: nothing has been destroyed, and the screen's Save is the commit point.
    expect(screen.queryByText('Confirm delete')).not.toBeInTheDocument();
  });

  it('shows a staged removal as restorable rather than gone', () => {
    const removed = staged(LINES);
    removed[0] = { ...removed[0], removed: true };

    render(<SalesOrderLinesEditor lines={LINES} editing={editing({ staged: removed })} />);

    expect(screen.getByText('Removed on save')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Restore CB6633/ })).toBeInTheDocument();
  });

  it('marks the line a blocking finding is about', () => {
    render(
      <SalesOrderLinesEditor lines={LINES} findings={[HARD]} editing={editing()} />,
    );

    expect(screen.getByText('Blocking')).toBeInTheDocument();
  });

  it('marks a line that has no product and no description', () => {
    const empty = staged(LINES).slice(0, 1);
    empty[0] = {
      ...empty[0],
      draft: { ...empty[0].draft, product_id: '', description: '' },
    };

    render(<SalesOrderLinesEditor lines={LINES.slice(0, 1)} editing={editing({ staged: empty })} />);

    expect(screen.getByText('Needed when no product is picked')).toBeInTheDocument();
  });

  it('marks a delivery date that is not an ISO day', () => {
    const wrong = staged(LINES).slice(0, 1);
    wrong[0] = { ...wrong[0], draft: { ...wrong[0].draft, delivery_date: '1/7/2026' } };

    render(<SalesOrderLinesEditor lines={LINES.slice(0, 1)} editing={editing({ staged: wrong })} />);

    expect(screen.getAllByText('Use YYYY-MM-DD').length).toBeGreaterThan(0);
  });
});

describe('the lines section keeps its chrome in both views', () => {
  it('renders the same heading and count while editing', () => {
    const read = render(<SalesOrderLinesTable lines={LINES} />);
    expect(within(read.container).getByText('2 lines')).toBeInTheDocument();
    read.unmount();

    const write = render(<SalesOrderLinesTable lines={LINES} editing={editing()} />);
    expect(within(write.container).getByText('Lines')).toBeInTheDocument();
    expect(within(write.container).getByText('2 lines')).toBeInTheDocument();
  });
});
