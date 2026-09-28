/**
 * #1341 - the scope lines table as the system DataGrid (AC-QF030 to AC-QF036).
 *
 * The owner: "this table needs to be datagrid". So the lines render through `PanelDataGrid`, the
 * component the Quotations list itself uses, and editing a line is a per-row Edit that opens the
 * row's editor in place, not a hand-written spreadsheet table.
 *
 * The grid writes nothing. It hands the whole line set back through `onChange`, which is what the
 * form page's one Save sends; every assertion on an edit is an assertion on that set.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { QuotationLine } from '../../_shared/types/project.types';
import {
  lineToFormLine,
  formLinesToBody,
  type QuotationFormLine,
} from '../../_shared/lib/quotationLineDraft';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const judgeQuotationLine = vi.fn();
vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/projectService')
  >();
  return {
    ...actual,
    judgeQuotationLine: (...args: unknown[]) => judgeQuotationLine(...args),
  };
});

const PRODUCTS = [
  {
    id: 'p9',
    product_code: 'SRT-BASIN-02',
    product_name: 'Counter basin',
    description: 'Vitreous china counter basin',
    brand_id: 'b1',
    base_uom_id: 'u1',
    list_price: '560.00',
  },
];
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForLineSelect: vi.fn(async () => PRODUCTS),
  getProductsForVariantSelect: vi.fn(async () => []),
}));
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [{ id: 'b1', brand_name: 'SORENTO' }] }),
}));
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query', () => ({
  useUOMSelectQuery: () => ({
    data: [
      { id: 'u1', uom_code: 'PCS', uom_name: 'Pieces' },
      { id: 'u2', uom_code: 'SET', uom_name: 'Sets' },
    ],
  }),
}));

import { QuotationLinesGrid } from './QuotationLinesGrid';

function line(overrides: Partial<QuotationLine> = {}): QuotationLine {
  return {
    id: 'l1',
    version_id: 'v1',
    product_id: 'p1',
    product_code: 'SRT-WC-01',
    description: 'Wall-hung WC',
    unit_price: '900.00',
    quantity: '10.00',
    line_total: '9000.00',
    is_non_standard: false,
    is_below_floor: false,
    sort_order: 0,
    ...overrides,
  };
}

let latest: QuotationFormLine[] = [];

function Harness({
  initial,
  editable,
}: {
  initial: QuotationFormLine[];
  editable: boolean;
}) {
  const [lines, setLines] = React.useState(initial);
  latest = lines;
  return (
    <QuotationLinesGrid
      lines={lines}
      onChange={
        editable
          ? (next) => {
              latest = next;
              setLines(next);
            }
          : undefined
      }
      quotationId="q1"
      listingKey="test::quotation-lines"
    />
  );
}

function renderGrid(lines: QuotationLine[], editable = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Harness initial={lines.map(lineToFormLine)} editable={editable} />
    </QueryClientProvider>,
  );
}

/** The item number cell of every line row (group header rows span the table). */
function itemNumbers(): string[] {
  return Array.from(document.querySelectorAll('tbody tr'))
    .filter((tr) => !tr.querySelector('td[colspan]'))
    .map((tr) => tr.querySelector('td')?.textContent ?? '');
}

beforeEach(() => {
  vi.clearAllMocks();
  latest = [];
  judgeQuotationLine.mockResolvedValue({
    is_non_standard: false,
    is_below_floor: false,
    floor_value: null,
    floor_level: null,
  });
});

describe('QuotationLinesGrid read', () => {
  it('AC-QF030: renders the lines through the system DataGrid with resizable, fixed columns', async () => {
    renderGrid([line()]);

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    const table = screen.getByRole('table');
    // The shared grid's fixed layout, not the hand-written line table's auto one.
    expect(table.className).toMatch(/table-fixed/);
    expect(screen.getByText('SRT-WC-01')).toBeInTheDocument();
    // A read offers nothing to press.
    expect(screen.queryByRole('button', { name: /Add a line/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Edit line/i })).toBeNull();
  });

  it('AC-QF032: draws a section heading as a band over the line that opens it', async () => {
    renderGrid([
      line({ id: 'l1', band_label: 'BILL NO 3 PAGE 15/4' }),
      line({ id: 'l2', product_code: 'BM107', description: 'Basin tap', sort_order: 1 }),
    ]);

    const bands = await screen.findAllByTestId('data-grid-group-header');
    expect(bands).toHaveLength(1);
    expect(bands[0]).toHaveTextContent('BILL NO 3 PAGE 15/4');
    expect(itemNumbers()).toEqual(['1', '2']);
  });

  it('AC-QF031: searches the lines and keeps each line its own item number', async () => {
    renderGrid([
      line({ id: 'l1' }),
      line({ id: 'l2', product_code: 'BM107', description: 'Basin tap body', sort_order: 1 }),
    ]);
    await screen.findByText('Wall-hung WC');

    fireEvent.change(screen.getByRole('searchbox', { name: /Search lines/i }), {
      target: { value: 'bm107' },
    });

    await waitFor(() => expect(screen.queryByText('Wall-hung WC')).not.toBeInTheDocument());
    expect(screen.getByText('Basin tap body')).toBeInTheDocument();
    expect(itemNumbers()).toEqual(['2']);
  });

  it('AC-QF035: totals the scope under the Total column, rate-only lines left out', async () => {
    renderGrid([
      line({ id: 'l1', unit_price: '250.00', quantity: '4.00', line_total: '1000.00' }),
      line({
        id: 'l2',
        unit_price: '180.00',
        quantity: '4.00',
        line_total: '720.00',
        is_rate_only: true,
        sort_order: 1,
      }),
    ]);
    await screen.findByText('rate only');

    const footer = document.querySelector('tfoot')?.textContent ?? '';
    expect(footer).toMatch(/1,000\.00/);
    expect(footer).not.toMatch(/1,720\.00/);
  });

  it('AC-QF036: an empty scope is an empty grid, with no Press Edit hint', async () => {
    renderGrid([]);

    expect(await screen.findByText(/No lines yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/Press Edit/i)).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('marks an off-catalog line and names the floor under a below-floor one', async () => {
    renderGrid([
      line({ id: 'l1', product_id: null, product_code: null, description: 'Bespoke top' }),
      line({
        id: 'l2',
        is_below_floor: true,
        floor_value_applied: '950.00',
        floor_level_applied: 'product',
        sort_order: 1,
      }),
    ]);

    expect(await screen.findByText('Off-catalog')).toBeInTheDocument();
    expect(screen.getByText('Below floor')).toBeInTheDocument();
  });
});

describe('QuotationLinesGrid edit', () => {
  it('AC-QF033: Add a line appends a line and opens its editor at once', async () => {
    renderGrid([], true);

    fireEvent.click(await screen.findByRole('button', { name: /Add a line/i }));

    const editor = await screen.findByRole('group', { name: 'Line 1' });
    expect(within(editor).getByLabelText('Description')).toBeInTheDocument();
    expect(latest).toHaveLength(1);
    expect(latest[0].id).toBeNull();
  });

  it('AC-QF033: Add a section appends a line with its section heading open', async () => {
    renderGrid([line()], true);

    fireEvent.click(await screen.findByRole('button', { name: /Add a section/i }));

    const editor = await screen.findByRole('group', { name: 'Line 2' });
    const heading = within(editor).getByLabelText('Section heading');
    expect(heading).toHaveFocus();
    fireEvent.change(heading, { target: { value: 'OPTIONAL ITEMS' } });
    expect(latest[1].draft.band_label).toBe('OPTIONAL ITEMS');
  });

  it('AC-QF034: per-row Edit opens that row, and a change reaches the set the form saves', async () => {
    renderGrid([line()], true);

    fireEvent.click(await screen.findByRole('button', { name: 'Edit line 1' }));
    const editor = await screen.findByRole('group', { name: 'Line 1' });
    fireEvent.change(within(editor).getByLabelText('Qty'), { target: { value: '12' } });
    fireEvent.change(within(editor).getByLabelText('Unit price'), { target: { value: '950.00' } });

    const body = formLinesToBody(latest);
    expect(body).toEqual([
      expect.objectContaining({ id: 'l1', quantity: '12', unit_price: '950.00' }),
    ]);
    // The row's own cells follow the draft, so the Total moves before anything is saved.
    await waitFor(() => expect(document.querySelector('tfoot')?.textContent).toMatch(/11,400\.00/));
  });

  it('AC-QF034: picking a product fills description, brand, UOM and list price', async () => {
    renderGrid([], true);
    fireEvent.click(await screen.findByRole('button', { name: /Add a line/i }));
    const editor = await screen.findByRole('group', { name: 'Line 1' });

    fireEvent.click(within(editor).getByRole('combobox', { name: 'Product' }));
    fireEvent.click(await screen.findByRole('option', { name: /SRT-BASIN-02/ }));

    await waitFor(() => expect(latest[0].draft.product_id).toBe('p9'));
    expect(latest[0].draft.description).toBe('Vitreous china counter basin');
    expect(latest[0].draft.brand_snapshot).toBe('SORENTO');
    expect(latest[0].draft.uom).toBe('PCS');
    expect(latest[0].draft.list_price).toBe('560.00');
  });

  it('AC-QF034: Remove takes the line out of the set, and the others renumber', async () => {
    renderGrid([line({ id: 'l1' }), line({ id: 'l2', description: 'Second', sort_order: 1 })], true);

    fireEvent.click(await screen.findByRole('button', { name: 'Edit line 1' }));
    const editor = await screen.findByRole('group', { name: 'Line 1' });
    fireEvent.click(within(editor).getByRole('button', { name: 'Remove line' }));

    expect(latest.map((row) => row.id)).toEqual(['l2']);
    await waitFor(() => expect(itemNumbers()).toEqual(['1']));
  });

  it('AC-QF017: an editable empty scope holds no line until one is added', async () => {
    renderGrid([], true);

    expect(await screen.findByRole('button', { name: /Add a line/i })).toBeInTheDocument();
    expect(itemNumbers()).toEqual([]);
    expect(latest).toEqual([]);
  });
});
