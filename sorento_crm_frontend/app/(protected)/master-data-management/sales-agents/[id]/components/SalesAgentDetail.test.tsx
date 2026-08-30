/**
 * The sales-agent record: its tabs, its edit-in-place, and the orders sold under the code.
 *
 * Three things this file exists to pin:
 *
 * 1. **View and edit are the same layout.** The Agent card's fields are collected in both
 *    views and compared as an ORDERED list. A field that moves, appears or disappears when
 *    Edit is pressed makes every edit start with re-finding the field, and a value that was
 *    visible and is now missing reads as data loss.
 * 2. **One save, every annotation.** The record edits six fields; the PATCH has to carry
 *    all six, with the location group upper-cased the way the backend stores it.
 * 3. **The Sales orders tab is THE sales-order table**, pinned to this agent - the same
 *    component the list is. So it is rendered for real here (its hooks stubbed), not
 *    mocked away: what is asserted is that the agent reaches the query, that the Agent
 *    column is gone, and that a row opens the order.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
Element.prototype.scrollIntoView = vi.fn();
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
}

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const push = vi.fn();
let searchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => '/master-data-management/sales-agents/agent-1',
  useSearchParams: () => searchParams,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

// `id` is forwarded so a real `<label htmlFor>` resolves and the field is reachable by its
// own name, the same stand-in the list's suite uses.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select id={props.id} value={props.value} onChange={(e) => props.onChange(e.target.value)}>
      <option value="">{props.placeholder ?? 'Not set'}</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('@/components/ui/date-range-picker', () => ({
  DateRangePicker: (props: { id?: string; placeholder?: string }) => (
    <button type="button" id={props.id}>
      {props.placeholder ?? 'Pick a date range'}
    </button>
  ),
}));

const EMPTY = { data: [], isLoading: false };
vi.mock('../../../../scm/hooks/useScmOptions', () => ({
  useCustomerOptions: () => EMPTY,
  useOrderTypeOptions: () => EMPTY,
  useProductOptions: () => EMPTY,
  useSupplierOptions: () => EMPTY,
  useCategoryOptions: () => EMPTY,
  useWarehouseOptions: () => EMPTY,
}));

const useSalesOrders = vi.fn();
vi.mock('../../../../scm/hooks/useSalesOrders', () => ({
  useSalesOrders: (...a: unknown[]) => useSalesOrders(...a),
  useSalesOrderAgents: () => ({ data: [], isLoading: false }),
  useCreateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useResetSalesOrderPlanning: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateDoFromSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

const hooks = vi.hoisted(() => ({
  useSalesAgent: vi.fn(),
  useSalesAgents: vi.fn(),
  useAnnotateSalesAgent: vi.fn(),
  useBulkAnnotateSalesAgents: vi.fn(),
  // The pager reads the list page through the entity's shared key + fetch (S3-03).
  salesAgentsPagerQuery: {
    listQueryKey: () => ['sales-agents', 'test-page'],
    fetchPage: vi.fn(),
  },
}));
vi.mock('../../hooks/useSalesAgents', () => hooks);

// The Transfers tab renders the SAME grid the Transfers page does; that component has its
// own tests, so here only the wiring (which agent it is pinned to) has to be proven.
vi.mock(
  '@/app/(protected)/inventory-management/stock-transfers/components/StockTransfersPanel',
  () => ({
    StockTransfersPanel: (props: { salesAgentId?: string }) => (
      <div data-testid="stock-transfers-panel" data-sales-agent={props.salesAgentId} />
    ),
  }),
);

import { SalesAgentDetail } from './SalesAgentDetail';
import type { SalesAgent } from '../../types/salesAgent.types';
import type { SalesOrder } from '@/app/(protected)/scm/types/scm.types';

function agent(over: Partial<SalesAgent> = {}): SalesAgent {
  return {
    id: 'agent-1',
    sales_agent: 'SEAN III',
    description: null,
    is_active: true,
    internal_note: null,
    follow_up: false,
    person_label: 'Sean',
    demand_class: 'project',
    location_group: 'BB',
    source: 'import',
    created_at: '2026-08-01T00:00:00',
    updated_at: null,
    ...over,
  };
}

function order(over: Partial<SalesOrder> = {}): SalesOrder {
  return {
    id: 'so-1',
    so_number: 'SO900001',
    order_type: 'project',
    order_type_label: 'Project',
    customer_code: '300-R009',
    customer_name: 'Rowenda Kitchen Sdn Bhd',
    market_segment: null,
    priority: 'normal',
    status: 'open',
    order_date: '2026-07-01',
    requested_delivery_date: '2026-09-01',
    total_qty: 12,
    committed_qty: 12,
    lines: [],
    source: 'upload',
    internal_note: null,
    stock_locations: [],
    linked_purchase_orders: [],
    created_at: '2026-07-01T00:00:00',
    ...over,
  } as SalesOrder;
}

const mutateAsync = vi.fn().mockResolvedValue(undefined);

function withAgent(row: SalesAgent | null, over: Record<string, unknown> = {}) {
  hooks.useSalesAgent.mockReturnValue({
    data: row ?? undefined,
    isLoading: false,
    isError: false,
    ...over,
  });
}

/** The page of the list the record pager walks. */
function withNeighbours(ids: string[]) {
  const page = {
    data: ids.map((id) => ({ id })),
    pagination: { total: ids.length, page: 1, limit: 50 },
  };
  hooks.useSalesAgents.mockReturnValue({ data: page });
  // The pager asks the entity for the page the URL names.
  hooks.salesAgentsPagerQuery.fetchPage.mockResolvedValue(page);
  pagerPage = page;
}

/** The page the pager should find in the cache, seeded per test. */
let pagerPage: { data: { id: string }[]; pagination: { total: number } } | null = null;

function withOrders(rows: SalesOrder[]) {
  useSalesOrders.mockReturnValue({
    data: {
      data: rows,
      pagination: { total: rows.length, page: 1, limit: 25 },
      empty: !rows.length,
    },
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  });
}

function renderDetail(id = 'agent-1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // The list page the pager walks, in the cache under the entity's own key -
  // exactly what the list leaves behind when the row is clicked.
  if (pagerPage) qc.setQueryData(['sales-agents', 'test-page'], pagerPage);
  return render(
    <QueryClientProvider client={qc}>
      <SalesAgentDetail id={id} />
    </QueryClientProvider>,
  );
}

/**
 * The Agent card's field labels, in the order they are rendered.
 *
 * A `Field`'s label is a `span.text-xs` reading, a `label.text-xs` editing. Badges carry
 * the same type scale, so they are excluded by their slot - otherwise the collector reads
 * "Project" and "BB" as labels, and they are values that become inputs.
 */
function agentFieldLabels(): string[] {
  const card = screen.getByRole('region', { name: 'Agent' });
  const nodes = card.querySelectorAll('label.text-xs, span.text-xs:not([data-slot="badge"])');
  return [...nodes].map((n) => n.textContent ?? '');
}

/**
 * Open the Sales orders tab.
 *
 * `mouseDown`, not `click`: Radix's tab trigger selects on mouse-down, and a plain `click`
 * in jsdom leaves the strip exactly where it was - which reads as a tab that holds nothing.
 */
async function openSalesOrdersTab() {
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'Sales orders' }), {
    button: 0,
    ctrlKey: false,
  });
  await screen.findByRole('tabpanel');
}

beforeEach(() => {
  push.mockReset();
  mutateAsync.mockClear().mockResolvedValue(undefined);
  useSalesOrders.mockReset();
  searchParams = new URLSearchParams();
  hooks.useSalesAgent.mockReset();
  hooks.useSalesAgents.mockReset();
  hooks.useAnnotateSalesAgent.mockReset();
  hooks.useAnnotateSalesAgent.mockReturnValue({ mutateAsync, isPending: false });
  withNeighbours(['agent-1']);
  withOrders([order()]);
});

describe('SalesAgentDetail - the record header and its tabs', () => {
  it('names the agent by its code and states whether it is still active', () => {
    withAgent(agent());
    renderDetail();

    // Twice over: the header names the record, and the Agent card states the same code as
    // the field that can never be edited.
    expect(screen.getAllByText('SEAN III').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Active').length).toBeGreaterThan(0);
  });

  it('says Inactive on a retired code', () => {
    withAgent(agent({ is_active: false }));
    renderDetail();

    expect(screen.getAllByText('Inactive').length).toBeGreaterThan(0);
  });

  it('shows the agent\'s stock transfers on their own tab, pinned to them (AC-E6)', () => {
    withAgent(agent());
    renderDetail();

    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Transfers' }), {
      button: 0,
      ctrlKey: false,
    });

    const panel = screen.getByTestId('stock-transfers-panel');
    expect(panel).toHaveAttribute('data-sales-agent', 'agent-1');
  });

  it('carries exactly three tabs, General first', () => {
    withAgent(agent());
    renderDetail();

    const tabs = screen.getAllByRole('tab').map((t) => t.textContent);
    expect(tabs).toEqual(['General', 'Sales orders', 'Transfers']);
  });

  it('renders every section, with an explicit empty state on the ones with nothing in them', () => {
    withAgent(agent({ person_label: null, demand_class: null, location_group: null }));
    renderDetail();

    expect(screen.getByRole('region', { name: 'Agent' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Notes' })).toBeInTheDocument();
    expect(screen.getAllByText('Not set').length).toBeGreaterThanOrEqual(4);
  });

  it('says so when the record is not there, instead of rendering an empty shell', () => {
    withAgent(null, { isError: true });
    renderDetail();

    expect(screen.getByText('Sales agent not found')).toBeInTheDocument();
  });
});

describe('SalesAgentDetail - view and edit are the same layout', () => {
  it('shows the same fields, in the same order, in both views', () => {
    withAgent(agent());
    renderDetail();

    const reading = agentFieldLabels();
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    expect(agentFieldLabels()).toEqual(reading);
    expect(reading).toEqual([
      'Agent code',
      'Person',
      'Demand class',
      'Location group',
      'Source',
      'Active',
      'Follow up',
    ]);
  });

  it('keeps the tab set identical while editing', () => {
    withAgent(agent());
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'General',
      'Sales orders',
      'Transfers',
    ]);
  });

  it('never offers the agent code as an input - it is what the documents state', () => {
    withAgent(agent());
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    expect(screen.queryByLabelText('Agent code')).not.toBeInTheDocument();
  });

  it('says nothing is written until Save is pressed', () => {
    withAgent(agent());
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    expect(screen.getByText('Nothing is written until you press Save.')).toBeInTheDocument();
  });
});

describe('SalesAgentDetail - saving', () => {
  it('sends every annotation the card edits, the location group upper-cased', async () => {
    withAgent(agent({ internal_note: 'Watch this one' }));
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Person'), { target: { value: 'Sean Lim' } });
    fireEvent.change(screen.getByLabelText('Location group'), { target: { value: 'hp' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save note' }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        id: 'agent-1',
        data: {
          person_label: 'Sean Lim',
          demand_class: 'project',
          location_group: 'HP',
          is_active: true,
          follow_up: false,
          internal_note: 'Watch this one',
        },
      }),
    );
  });

  it('retires the code when Active is switched off', async () => {
    withAgent(agent());
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.click(screen.getByRole('switch', { name: 'Active' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save note' }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ data: expect.objectContaining({ is_active: false }) }),
      ),
    );
  });

  it('sends an explicit null for a field cleared to nothing', async () => {
    withAgent(agent());
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Demand class'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Person'), { target: { value: '  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save note' }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({ demand_class: null, person_label: null }),
        }),
      ),
    );
  });

  it('writes nothing on Cancel and puts the stored value back', () => {
    withAgent(agent());
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Person'), { target: { value: 'Typed away' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(mutateAsync).not.toHaveBeenCalled();
    expect(screen.queryByText('Typed away')).not.toBeInTheDocument();
    expect(screen.getByText('Sean')).toBeInTheDocument();
  });

  it('opens straight into the edit session on ?edit=1', () => {
    searchParams = new URLSearchParams('edit=1');
    withAgent(agent());
    renderDetail();

    expect(screen.getByLabelText('Person')).toBeInTheDocument();
  });
});

describe('SalesAgentDetail - the Sales orders tab', () => {
  it('asks for THIS agent orders and nobody else', async () => {
    withAgent(agent());
    renderDetail();
    await openSalesOrdersTab();

    const params = useSalesOrders.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(params.salesAgentId).toBe('agent-1');
  });

  it('lists them, and the row opens the order', async () => {
    withAgent(agent());
    renderDetail();
    await openSalesOrdersTab();

    expect(await screen.findByText('SO900001')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Rowenda Kitchen Sdn Bhd'));

    expect(push).toHaveBeenCalledWith(expect.stringContaining('/scm/sales-orders/so-1'));
  });

  it('carries the agent into the order URL, so its pager walks this agent orders', async () => {
    withAgent(agent());
    renderDetail();
    await openSalesOrdersTab();

    fireEvent.click(screen.getByText('Rowenda Kitchen Sdn Bhd'));

    const href = push.mock.calls.at(-1)?.[0] as string;
    expect(new URLSearchParams(href.split('?')[1] ?? '').get('sales_agent_id')).toBe('agent-1');
  });

  it('drops the Agent column - every row would repeat the code at the top of the page', async () => {
    withAgent(agent());
    renderDetail();
    await openSalesOrdersTab();

    const panel = screen.getByRole('tabpanel');
    expect(within(panel).queryByRole('columnheader', { name: 'Agent' })).not.toBeInTheDocument();
    expect(within(panel).getByRole('columnheader', { name: /SO number/ })).toBeInTheDocument();
  });

  it('offers neither Add nor the book-wide upload from inside one agent record', async () => {
    withAgent(agent());
    renderDetail();
    await openSalesOrdersTab();

    expect(screen.queryByRole('button', { name: 'Add sales order' })).not.toBeInTheDocument();
  });

  it('says the agent has none rather than pointing at an upload', async () => {
    withAgent(agent());
    withOrders([]);
    renderDetail();
    await openSalesOrdersTab();

    expect(await screen.findByText('No sales orders for this agent.')).toBeInTheDocument();
  });
});

describe('SalesAgentDetail - walking the list', () => {
  it('S3-04: shows the pager disabled at both ends when the page holds one record', () => {
    withAgent(agent());
    withNeighbours(['agent-1']);
    renderDetail();

    // The shared pager states the position ("1 / 1") rather than vanishing: it
    // disappears only when the record is not on the page the URL names (S3-05).
    expect(screen.getByRole('button', { name: 'Next sales agent' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Previous sales agent' })).toBeDisabled();
  });

  it('steps to the next record on the page, carrying the list query', () => {
    searchParams = new URLSearchParams('page=1&limit=50&sort=sales_agent&dir=asc');
    withAgent(agent());
    withNeighbours(['agent-1', 'agent-2']);
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: 'Next sales agent' }));

    expect(push).toHaveBeenCalledWith(
      '/master-data-management/sales-agents/agent-2?page=1&limit=50&sort=sales_agent&dir=asc',
    );
  });

  it('stops at the end of the page rather than wrapping to its start', () => {
    withAgent(agent({ id: 'agent-2' }));
    withNeighbours(['agent-1', 'agent-2']);
    renderDetail('agent-2');

    expect(screen.getByRole('button', { name: 'Next sales agent' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Previous sales agent' })).toBeEnabled();
  });
});
