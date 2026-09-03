/**
 * The shared SCM lightbox (R7, AC-B1-B7) and the two SPO-planner pickers (R21, AC-G1/AC-G2).
 *
 * The data hooks are mocked, never a QueryClient: these are the dialog's STATES (loading,
 * empty, rows, totals, tab switch, tick), and a real query would make the tests about
 * react-query's timing instead.
 *
 * S9 (3 Sep): every body now renders on the repo's `DataGrid`, which calls
 * `useListingColumnPreferences` (a `useQuery`/`useQueryClient` pair) even with
 * `listingKey={null}` - `renderWithClient` supplies the `QueryClientProvider` that needs.
 * `next/navigation`'s `usePathname` (the grid's own pathname fallback, never actually read
 * here since every call passes `listingKey={null}`) is stubbed for a stable value rather than
 * left to jsdom's default of returning `null` outside an app router.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
Element.prototype.setPointerCapture = Element.prototype.setPointerCapture ?? (() => {});
Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture ?? (() => {});
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/loading-plan',
}));

const useContainerRequestDrill = vi.fn();
vi.mock('../hooks/useContainerRequestDrill', () => ({
  useContainerRequestDrill: (...a: unknown[]) => useContainerRequestDrill(...a),
}));

const useLocationStock = vi.fn();
vi.mock('../reorder/hooks/useReorderRun', () => ({
  useLocationStock: (...a: unknown[]) => useLocationStock(...a),
}));

vi.mock('../../project-sales/fulfilment-planning/components/StockDocumentsPanel', () => ({
  // Addressed by ids: the panel no longer takes a code at all, since the heading block that
  // printed one was removed (captain, 30 August 2026).
  StockDocumentsPanel: ({ warehouseId }: { warehouseId: string }) => (
    <div data-testid="stock-documents">{`documents for ${warehouseId}`}</div>
  ),
}));

import {
  IncomingPlTable,
  NO_SPO_TO_POOL,
  OnHandTable,
  PlanRowDialog,
  PoTabs,
  PoTakesPicker,
  ProjectRetailTabs,
  SoCoveragePicker,
  SpoTabs,
  monthLabel,
  type PlanDemandLineRow,
  type PlanHistoryPoint,
} from './PlanRowDialog';
import { PlanNumberButton } from './PlanNumberButton';

/** Radix's TabsTrigger switches on mouse down; a bare `click` leaves the old panel up. */
function switchTab(name: string) {
  const tab = screen.getByRole('tab', { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
}

function drill(over: Record<string, unknown> = {}) {
  return { data: { rows: [], total: 0, history: [] }, isLoading: false, ...over };
}

beforeEach(() => {
  useContainerRequestDrill.mockReset();
  useContainerRequestDrill.mockReturnValue(drill());
  useLocationStock.mockReset();
  useLocationStock.mockReturnValue({ data: undefined, isLoading: false });
});

// ---------------------------------------------------------------------------
// The shell
// ---------------------------------------------------------------------------

describe('PlanRowDialog', () => {
  it('titles itself "<Kind> · <product code>" with the product name as the description, and no header context (S3, AC-C4)', () => {
    renderWithClient(
      <PlanRowDialog
        kind="spo"
        productCode="SRTWB241"
        productName="Wall hung basin 241"
        onOpenChange={() => {}}
      >
        <p>body</p>
      </PlanRowDialog>,
    );

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/SPO · SRTWB241/)).toBeTruthy();
    expect(within(dialog).getByText('Wall hung basin 241')).toBeTruthy();
    expect(within(dialog).getByText('body')).toBeTruthy();
  });

  it('closes on Escape', () => {
    const onOpenChange = vi.fn();
    renderWithClient(
      <PlanRowDialog kind="po" productCode="SRTWB241" onOpenChange={onOpenChange}>
        <p>body</p>
      </PlanRowDialog>,
    );

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape', code: 'Escape' });

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('renders nothing when it is not open', () => {
    renderWithClient(
      <PlanRowDialog kind="po" productCode="SRTWB241" open={false} onOpenChange={() => {}}>
        <p>body</p>
      </PlanRowDialog>,
    );

    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('PlanNumberButton', () => {
  it('is the number itself, and opens the dialog without clicking the row through it', () => {
    const onClick = vi.fn();
    const onRowClick = vi.fn();
    renderWithClient(
      <div onClick={onRowClick}>
        <PlanNumberButton value="117" label="SPO for SRTWB241" onClick={onClick} />
      </div>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'SPO for SRTWB241' }));

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('is plain text on a row with nothing to open', () => {
    renderWithClient(<PlanNumberButton value="117" label="SPO" onClick={() => {}} disabled />);

    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText('117')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Project / Retail
// ---------------------------------------------------------------------------

const LINES: PlanDemandLineRow[] = [
  {
    so_number: 'SO404118',
    customer: 'PEMBINAAN MAJU SDN BHD',
    project: 'Taman Sri Bayu Ph2',
    agent: 'SEAN',
    price: 318,
    qty: 1200,
    required_date: '2026-09-30',
  },
  {
    so_number: 'SO403990',
    customer: 'E-REGION BUILDER SDN BHD',
    project: 'Bandar Rimbayu',
    agent: 'LCL',
    price: 312,
    qty: 900,
    required_date: '2026-10-15',
  },
];

const HISTORY: PlanHistoryPoint[] = [
  { month: '2026-02', project_qty: 300, retail_qty: 120 },
  { month: '2026-03', project_qty: 1504, retail_qty: 200 },
  { month: '2026-07', project_qty: 400, retail_qty: 701 },
];

describe('ProjectRetailTabs', () => {
  it('lists the open lines and foots them to the figure the cell shows, its tab naming the sum (S3, AC-C1)', () => {
    renderWithClient(<ProjectRetailTabs channel="project" lines={LINES} history={HISTORY} />);

    expect(screen.getByRole('tab', { name: 'Open (2,100)' })).toBeTruthy();
    expect(screen.getByText('SO404118')).toBeTruthy();
    expect(screen.getByText('Taman Sri Bayu Ph2')).toBeTruthy();
    expect(screen.getByText('Total')).toBeTruthy();
    expect(screen.getByText('2,100')).toBeTruthy();
  });

  it('names the cut-off in the open tab when a horizon is set (S3, AC-C1)', () => {
    renderWithClient(
      <ProjectRetailTabs channel="project" lines={LINES} history={HISTORY} horizon="2026-10-31" />,
    );

    expect(screen.getByRole('tab', { name: 'Open before cut-off 31/10/2026 (2,100)' })).toBeTruthy();
  });

  it('says so when the channel has nothing open', () => {
    renderWithClient(<ProjectRetailTabs channel="retail" lines={[]} history={[]} />);

    expect(screen.getByText('Nothing open on this channel for this product.')).toBeTruthy();
  });

  it('shows skeletons while the payload is still coming', () => {
    const { container } = renderWithClient(
      <ProjectRetailTabs channel="retail" lines={[]} history={[]} loading />,
    );

    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });

  it('marks each column\'s own peak cell, on whichever row it fell, with no peak text line (S1, AC-A1/A2)', () => {
    const { container } = renderWithClient(
      <ProjectRetailTabs channel="project" lines={LINES} history={HISTORY} />,
    );

    switchTab('12-month history');

    expect(screen.queryByText(/Project peak/)).toBeNull();
    expect(screen.queryByText(/Retail peak/)).toBeNull();

    const projectPeak = container.querySelector('[data-peak="project"]');
    const retailPeak = container.querySelector('[data-peak="retail"]');
    expect(projectPeak?.textContent).toBe('1,504');
    expect(projectPeak?.closest('tr')).toHaveTextContent('Mar 26');
    expect(retailPeak?.textContent).toBe('701');
    expect(retailPeak?.closest('tr')).toHaveTextContent('Jul 26');
  });

  it('marks both peaks on the same row when they coincide (S1)', () => {
    const sameRow: PlanHistoryPoint[] = [
      { month: '2026-02', project_qty: 100, retail_qty: 50 },
      { month: '2026-03', project_qty: 900, retail_qty: 400 },
    ];
    const { container } = renderWithClient(
      <ProjectRetailTabs channel="project" lines={[]} history={sameRow} />,
    );

    switchTab('12-month history');

    const projectPeak = container.querySelector('[data-peak="project"]');
    const retailPeak = container.querySelector('[data-peak="retail"]');
    expect(projectPeak?.closest('tr')).toBe(retailPeak?.closest('tr'));
  });

  it('the first of a tie wins, and a column that never rises above 0 marks nothing (S1, AC-A2)', () => {
    const tie: PlanHistoryPoint[] = [
      { month: '2026-02', project_qty: 300, retail_qty: 0 },
      { month: '2026-03', project_qty: 1504, retail_qty: 0 },
      { month: '2026-04', project_qty: 1504, retail_qty: 0 },
    ];
    const { container } = renderWithClient(
      <ProjectRetailTabs channel="project" lines={[]} history={tie} />,
    );

    switchTab('12-month history');

    const projectPeaks = container.querySelectorAll('[data-peak="project"]');
    expect(projectPeaks.length).toBe(1);
    expect(projectPeaks[0].closest('tr')).toHaveTextContent('Mar 26');
    expect(container.querySelectorAll('[data-peak="retail"]').length).toBe(0);
  });

  it('foots the 12-month history to BOTH series (AC-A3/AC-J3)', () => {
    renderWithClient(<ProjectRetailTabs channel="project" lines={LINES} history={HISTORY} />);

    switchTab('12-month history');

    // 300 + 1,504 + 400 project; 120 + 200 + 701 retail.
    const footer = screen.getByText('Total').closest('tr') as HTMLElement;
    expect(within(footer).getByText('2,204')).toBeTruthy();
    expect(within(footer).getByText('1,021')).toBeTruthy();
  });

  it('opens directly on the history tab when the trigger asked for it (AC-B6)', () => {
    renderWithClient(
      <ProjectRetailTabs channel="retail" lines={LINES} history={HISTORY} initialTab="history" />,
    );

    expect(screen.getByRole('tab', { name: '12-month history' })).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(screen.getByText('Mar 26')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Need - project and retail together (S2)
// ---------------------------------------------------------------------------

describe('ProjectRetailTabs - the Need channel', () => {
  const NEED_LINES: PlanDemandLineRow[] = [
    { ...LINES[0], channel: 'project' },
    { ...LINES[1], channel: 'retail' },
  ];

  it('is titled "Need · <code>" by the shell and lists both channels with a Channel column (AC-B1/AC-B2)', () => {
    renderWithClient(
      <PlanRowDialog kind="need" productCode="SRTWB241" onOpenChange={() => {}}>
        <ProjectRetailTabs channel="need" lines={NEED_LINES} history={HISTORY} />
      </PlanRowDialog>,
    );

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/Need · SRTWB241/)).toBeTruthy();
    expect(within(dialog).getByText('Channel')).toBeTruthy();
    expect(within(dialog).getByText('SO404118')).toBeTruthy();
    expect(within(dialog).getByText('SO403990')).toBeTruthy();
    // The Total foots to the Need figure, project and retail together.
    expect(within(dialog).getByText('Total').closest('tr')).toHaveTextContent('2,100');
  });

  it('history carries a Total column, and its own peak (AC-B3)', () => {
    const { container } = renderWithClient(
      <ProjectRetailTabs channel="need" lines={NEED_LINES} history={HISTORY} />,
    );

    switchTab('12-month history');

    expect(screen.getByRole('columnheader', { name: 'Total' })).toBeTruthy();
    // Totals per month: 420, 1,704, 1,101 - the peak is Mar 26.
    const totalPeak = container.querySelector('[data-peak="total"]');
    expect(totalPeak?.textContent).toBe('1,704');
    expect(totalPeak?.closest('tr')).toHaveTextContent('Mar 26');
    // The project and retail peaks are still marked too.
    expect(container.querySelector('[data-peak="project"]')?.textContent).toBe('1,504');
    expect(container.querySelector('[data-peak="retail"]')?.textContent).toBe('701');
    // The footer row sums the Total column too: 2,204 project + 1,021 retail.
    const footerRow = container.querySelector('tfoot tr') as HTMLElement;
    expect(within(footerRow).getByText('3,225')).toBeTruthy();
  });
});

describe('monthLabel', () => {
  it('reads a month bucket as a month, never as a date', () => {
    expect(monthLabel('2026-03')).toBe('Mar 26');
    expect(monthLabel(null)).toBe('-');
  });
});

// ---------------------------------------------------------------------------
// On hand
// ---------------------------------------------------------------------------

describe('OnHandTable', () => {
  it('shows the site pools only, foots them, and dates the reading', () => {
    useLocationStock.mockReturnValue({
      data: {
        product_id: 'p1',
        as_of: '2026-08-27T06:05:00',
        locations: [
          {
            warehouse_id: 'w1',
            warehouse_code: 'BRW',
            on_hand: 201,
            reserved: 0,
            free: 201,
            so_qty: 96,
            spo_qty: 90,
            available: 105,
            is_pool: true,
          },
          {
            warehouse_id: 'w2',
            warehouse_code: 'BRW-BB',
            on_hand: 500,
            reserved: 0,
            free: 500,
            so_qty: 0,
            spo_qty: 0,
            available: 500,
            is_pool: false,
          },
        ],
      },
      isLoading: false,
    });

    renderWithClient(<OnHandTable productId="p1" />);

    expect(screen.getByText('BRW')).toBeTruthy();
    expect(screen.queryByText('BRW-BB')).toBeNull();
    const footer = screen.getByText('Site pools').closest('tr') as HTMLElement;
    expect(within(footer).getByText('201')).toBeTruthy();
    expect(screen.getByText(/Stock as of/)).toBeTruthy();
  });

  it('expands a location to the documents behind it', () => {
    useLocationStock.mockReturnValue({
      data: {
        product_id: 'p1',
        as_of: null,
        locations: [
          {
            warehouse_id: 'w1',
            warehouse_code: 'BRW',
            on_hand: 201,
            reserved: 0,
            free: 201,
            so_qty: 0,
            spo_qty: 0,
            available: 201,
            is_pool: true,
          },
        ],
      },
      isLoading: false,
    });

    renderWithClient(<OnHandTable productId="p1" />);
    expect(screen.queryByTestId('stock-documents')).toBeNull();

    fireEvent.click(screen.getByText('BRW'));

    expect(screen.getByTestId('stock-documents').textContent).toBe('documents for w1');
  });

  it('says so when the product has no stock row anywhere', () => {
    useLocationStock.mockReturnValue({
      data: { product_id: 'p1', as_of: null, locations: [] },
      isLoading: false,
    });

    renderWithClient(<OnHandTable productId="p1" />);

    expect(screen.getByText('No stock rows for this product.')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// The three drill bodies
// ---------------------------------------------------------------------------

describe('SpoTabs', () => {
  const rows = [
    {
      spo_number: 'CRM-SPO-e372b1e9',
      shipment_id: 's1',
      shipment_number: 'FSCU8103365',
      warehouse_code: 'BRW',
      qty: 90,
      received: 0,
      eta: '2026-07-27',
      arrived_at: null,
      status: 'in_transit',
    },
    {
      spo_number: 'CRM-SPO-1a0c77',
      shipment_id: 's2',
      shipment_number: null,
      warehouse_code: 'WH3',
      qty: 27,
      received: 0,
      eta: null,
      arrived_at: null,
      status: 'draft',
    },
  ];

  it('asks the drill for this supplier, product and kind', () => {
    renderWithClient(<SpoTabs supplierId="sup1" productId="p1" />);

    expect(useContainerRequestDrill).toHaveBeenCalledWith('sup1', 'p1', 'spo');
  });

  it('lists what is on the water and foots it to the cell, naming the sum in the tab (S3, AC-C2)', () => {
    useContainerRequestDrill.mockReturnValue(drill({ data: { rows, total: 117, history: [] } }));

    renderWithClient(<SpoTabs supplierId="sup1" productId="p1" />);

    expect(screen.getByRole('tab', { name: 'Open to pools (117)' })).toBeTruthy();
    expect(screen.getByText('CRM-SPO-e372b1e9')).toBeTruthy();
    expect(screen.getByText('FSCU8103365')).toBeTruthy();
    // A packing list nobody has numbered reads as a draft, never as a blank.
    expect(screen.getByText('Draft')).toBeTruthy();
    expect(screen.getByText('117')).toBeTruthy();
  });

  it('says the SPO sentence when nothing is on its way to a pool', () => {
    renderWithClient(<SpoTabs supplierId="sup1" productId="p1" />);

    expect(screen.getByText(NO_SPO_TO_POOL)).toBeTruthy();
  });

  it('switches to the landed shipments, naming the sum of what landed (S3, AC-C2)', () => {
    useContainerRequestDrill.mockReturnValue(
      drill({
        data: {
          rows: [],
          total: 0,
          history: [{ ...rows[0], qty: 40, received: 40, arrived_at: '2026-06-01' }],
        },
      }),
    );

    renderWithClient(<SpoTabs supplierId="sup1" productId="p1" />);
    switchTab('History (40)');

    const row = screen.getByText('CRM-SPO-e372b1e9').closest('tr') as HTMLElement;
    expect(within(row).getAllByText('40').length).toBe(2); // qty and received

    // AC-J3: the history tab foots its own qty too, not only the open one - there is no
    // cell total for a landed shipment, so it sums its own rows.
    const footer = screen.getByText('Total').closest('tr') as HTMLElement;
    expect(within(footer).getByText('40')).toBeTruthy();
  });

  it('shows skeletons while the drill is loading', () => {
    useContainerRequestDrill.mockReturnValue(drill({ data: undefined, isLoading: true }));

    const { container } = renderWithClient(<SpoTabs supplierId="sup1" productId="p1" />);

    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });
});

describe('IncomingPlTable', () => {
  const rows = [
    {
      shipment_id: 's1',
      shipment_number: 'FSCU8103365',
      container_number: 'FSCU8103365',
      supplier_name: 'JINBAICHUAN',
      qty: 399,
      eta: '2026-07-27',
      status: 'in_transit',
    },
    {
      shipment_id: 's2',
      shipment_number: 'PL-2608-001',
      container_number: null,
      supplier_name: 'JINBAICHUAN',
      qty: 200,
      eta: null,
      status: 'draft',
    },
  ];

  it('lists the unreceived packing lists and foots them to the cell', () => {
    useContainerRequestDrill.mockReturnValue(drill({ data: { rows, total: 599, history: [] } }));

    renderWithClient(<IncomingPlTable supplierId="sup1" productId="p1" />);

    expect(useContainerRequestDrill).toHaveBeenCalledWith('sup1', 'p1', 'incoming_pl');
    expect(screen.getByText('PL-2608-001')).toBeTruthy();
    expect(screen.getByText('599')).toBeTruthy();
  });

  it('opens the packing list when the caller can navigate to one', () => {
    const onOpenShipment = vi.fn();
    useContainerRequestDrill.mockReturnValue(drill({ data: { rows, total: 599, history: [] } }));

    renderWithClient(
      <IncomingPlTable supplierId="sup1" productId="p1" onOpenShipment={onOpenShipment} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'FSCU8103365' }));

    expect(onOpenShipment).toHaveBeenCalledWith('s1');
  });

  it('says so when nothing is on its way', () => {
    renderWithClient(<IncomingPlTable supplierId="sup1" productId="p1" />);

    expect(
      screen.getByText('Nothing is on its way on a packing list for this product.'),
    ).toBeTruthy();
  });
});

describe('PoTabs', () => {
  const open = [
    {
      purchase_order_id: 'po1',
      po_number: 'PO-24118',
      supplier_name: 'JINBAICHUAN',
      qty_ordered: 200,
      still_to_come: 143,
      unit_price: 335,
      currency: 'CNY',
      issued: '2026-04-28',
      eta: '2026-09-15',
      status: 'partial',
    },
  ];

  it('lists the open lines, prices them in the PO currency and foots still-to-come, naming the sum in the tab (S3, AC-C3)', () => {
    useContainerRequestDrill.mockReturnValue(drill({ data: { rows: open, total: 143, history: [] } }));

    renderWithClient(<PoTabs supplierId="sup1" productId="p1" />);

    expect(useContainerRequestDrill).toHaveBeenCalledWith('sup1', 'p1', 'po');
    expect(screen.getByRole('tab', { name: 'Open (143)' })).toBeTruthy();
    expect(screen.getByText('PO-24118')).toBeTruthy();
    expect(screen.getByText(/CNY/)).toBeTruthy();
    const footer = screen.getByText('Total still to come').closest('tr') as HTMLElement;
    expect(within(footer).getByText('143')).toBeTruthy();
  });

  it('switches to what was ordered before, naming the quantity that WAS ordered (S3, AC-C3)', () => {
    useContainerRequestDrill.mockReturnValue(
      drill({
        data: {
          rows: [],
          total: 0,
          history: [{ ...open[0], po_number: 'PO-24090', still_to_come: 0, status: 'closed' }],
        },
      }),
    );

    renderWithClient(<PoTabs supplierId="sup1" productId="p1" />);
    // Sums qty_ordered, not still-to-come - a closed PO's still-to-come is always 0.
    switchTab('History (200)');

    expect(screen.getByText('PO-24090')).toBeTruthy();

    // AC-J3: the history tab foots its own still-to-come too (here, a closed PO: 0).
    const footer = screen.getByText('Total still to come').closest('tr') as HTMLElement;
    expect(within(footer).getByText('0')).toBeTruthy();
  });

  it('says so when nothing is on order', () => {
    renderWithClient(<PoTabs supplierId="sup1" productId="p1" />);

    expect(screen.getByText('Nothing is on order for this product.')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// The SPO planner's two pickers
// ---------------------------------------------------------------------------

describe('PoTakesPicker', () => {
  const takes = [
    {
      po_line_id: 'l1',
      po_number: 'PO-24118',
      supplier_name: 'JINBAICHUAN',
      po_date: '2026-04-28',
      expected_date: '2026-09-15',
      qty: 40,
      open_qty: 150,
    },
    {
      po_line_id: 'l2',
      po_number: 'PO-24090',
      supplier_name: 'JINBAICHUAN',
      po_date: '2026-03-30',
      expected_date: null,
      qty: 20,
      open_qty: 20,
    },
  ];

  it('pre-ticks the suggested takes and counts them in the footer', () => {
    renderWithClient(
      <PoTakesPicker
        takes={takes}
        tickedIds={['l1']}
        onChange={() => {}}
        coveredQty={40}
        packedQty={60}
      />,
    );

    expect(screen.getByLabelText('Draw from PO-24118')).toBeChecked();
    expect(screen.getByLabelText('Draw from PO-24090')).not.toBeChecked();
    expect(screen.getByText('1 of 2 POs · covers 40 of packed 60')).toBeTruthy();

    // AC-J3: the table itself also foots the Taken column, beside the existing sentence.
    const footer = screen.getByText('Total').closest('tr') as HTMLElement;
    expect(within(footer).getByText('40')).toBeTruthy();
  });

  it('hands the whole tick set back when one is turned on', () => {
    const onChange = vi.fn();
    renderWithClient(
      <PoTakesPicker
        takes={takes}
        tickedIds={['l1']}
        onChange={onChange}
        coveredQty={40}
        packedQty={60}
      />,
    );

    fireEvent.click(screen.getByLabelText('Draw from PO-24090'));

    expect(onChange).toHaveBeenCalledWith(['l1', 'l2']);
  });

  it('hands back the remainder when one is turned off', () => {
    const onChange = vi.fn();
    renderWithClient(
      <PoTakesPicker
        takes={takes}
        tickedIds={['l1', 'l2']}
        onChange={onChange}
        coveredQty={60}
        packedQty={60}
      />,
    );

    fireEvent.click(screen.getByLabelText('Draw from PO-24118'));

    expect(onChange).toHaveBeenCalledWith(['l2']);
  });

  it('says so when no open PO can back the line', () => {
    renderWithClient(
      <PoTakesPicker takes={[]} tickedIds={[]} onChange={() => {}} coveredQty={0} packedQty={60} />,
    );

    expect(screen.getByText('No open PO can back this line.')).toBeTruthy();
  });
});

describe('SoCoveragePicker', () => {
  const coverage = [
    {
      key: 'project:1',
      kind: 'project' as const,
      document: 'OI-0042',
      customer_name: 'PEMBINAAN MAJU',
      required_date: '2026-09-30',
      qty: 40,
      warehouse_code: 'BRW',
    },
    {
      key: 'retail:2',
      kind: 'retail' as const,
      document: 'SO404352',
      customer_name: 'SYARIKAT PERNIAGAAN KL',
      required_date: '2026-09-20',
      qty: 20,
      warehouse_code: null,
    },
  ];

  it('lists project first then retail, pre-ticked, with the unassigned remainder stated', () => {
    renderWithClient(
      <SoCoveragePicker
        coverage={coverage}
        tickedKeys={['project:1']}
        onChange={() => {}}
        unassigned={20}
      />,
    );

    const rows = screen.getAllByRole('row');
    expect(rows[1].textContent).toContain('OI-0042');
    expect(rows[2].textContent).toContain('SO404352');
    expect(screen.getByLabelText('Cover OI-0042')).toBeChecked();
    expect(screen.getByText('Unassigned 20')).toBeTruthy();

    // AC-J3: the Open column foots too (40 + 20), beside the existing Unassigned line.
    const footer = screen.getByText('Total').closest('tr') as HTMLElement;
    expect(within(footer).getByText('60')).toBeTruthy();
  });

  it('hands the whole tick set back on a change', () => {
    const onChange = vi.fn();
    renderWithClient(
      <SoCoveragePicker
        coverage={coverage}
        tickedKeys={['project:1']}
        onChange={onChange}
        unassigned={20}
      />,
    );

    fireEvent.click(screen.getByLabelText('Cover SO404352'));

    expect(onChange).toHaveBeenCalledWith(['project:1', 'retail:2']);
  });

  it('says so when there is no open demand to point at', () => {
    renderWithClient(
      <SoCoveragePicker coverage={[]} tickedKeys={[]} onChange={() => {}} unassigned={0} />,
    );

    expect(screen.getByText('No open demand this SPO could cover.')).toBeTruthy();
  });
});
