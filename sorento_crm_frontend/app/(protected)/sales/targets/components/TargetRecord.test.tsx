/**
 * The target record, `/sales/targets/{id}` and `/sales/targets/new` (UAC S1-18, S1-23 to
 * S1-28; the S1 hand test of 27 Sep, F1, F4, F5, F6).
 *
 * ONE record view for create, view and edit, no modal: a header card, then line tabs in the
 * order Details, Periods, Agents (a team target only), Commission. Create opens the same view
 * empty with the defaults Amount, Invoiced, All products, today to month end, split off. Edit is
 * an item in the gear dropdown. Every pick is the system SearchableSelect or
 * SearchableMultiSelect, and a picked category, product or brand always shows its name.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

const router = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/sales/targets/t1',
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/helpers', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/helpers')>()),
  todayMalaysiaYyyyMmDd: () => '2026-10-20',
}));

vi.mock('@/components/common/DetailActions', () => ({
  default: ({
    pagerNode,
    actions,
    primary,
    pendingAction,
  }: {
    pagerNode?: React.ReactNode;
    actions?: { key: string; label: string; run: () => void }[];
    primary?: React.ReactNode;
    pendingAction?: React.ReactNode;
  }) => (
    <div data-testid="detail-actions">
      {pagerNode}
      <div data-testid="gear">
        {(actions ?? []).map((a) => (
          <button key={a.key} type="button" onClick={() => a.run()}>
            {a.label}
          </button>
        ))}
      </div>
      {pendingAction ?? primary}
    </div>
  ),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    disabled?: boolean;
    'aria-label'?: string;
  }) => (
    <select
      id={props.id}
      aria-label={props['aria-label']}
      value={props.value}
      disabled={props.disabled}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="">None</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

// The real component's fallback, kept: a picked value with no known option renders its raw
// value as the chip, which is exactly how a UUID reached the screen (F5).
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    id?: string;
    value: string[];
    onChange: (v: string[]) => void;
    options?: { value: string; label: string }[];
    selectedOptions?: { value: string; label: string }[];
  }) => {
    const known = new Map(
      [...(props.options ?? []), ...(props.selectedOptions ?? [])].map((o) => [o.value, o.label]),
    );
    return (
      <div role="group" aria-labelledby={`${props.id}-label`} id={props.id}>
        {props.value.map((v) => (
          <span key={v} data-testid="chip">
            {known.get(v) ?? v}
          </span>
        ))}
        {(props.options ?? []).map((o) => (
          <label key={o.value}>
            <input
              type="checkbox"
              checked={props.value.includes(o.value)}
              onChange={(e) =>
                props.onChange(
                  e.target.checked ? [...props.value, o.value] : props.value.filter((x) => x !== o.value),
                )
              }
            />
            {o.label}
          </label>
        ))}
      </div>
    );
  },
}));

vi.mock('@/components/ui/date-range-picker', () => ({
  DateRangePicker: (props: {
    from?: string | null;
    to?: string | null;
    onChange: (next: { from: string | null; to: string | null }) => void;
  }) => (
    <span>
      <input
        aria-label="Start date"
        value={props.from ?? ''}
        onChange={(e) => props.onChange({ from: e.target.value || null, to: props.to ?? null })}
      />
      <input
        aria-label="End date"
        value={props.to ?? ''}
        onChange={(e) => props.onChange({ from: props.from ?? null, to: e.target.value || null })}
      />
    </span>
  ),
}));

const perms = vi.hoisted(() => ({ granted: new Set<string>() }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => perms.granted.has(slug),
}));

const create = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
const patchHeader = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
const patchPeriod = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
const addChild = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
const productSearch = vi.hoisted(() => vi.fn());
const customerSearch = vi.hoisted(() => vi.fn());
const hooks = vi.hoisted(() => ({
  useTargetCustomerSearch: () => customerSearch,
  useSalesTarget: vi.fn(),
  useSalesTargets: vi.fn(),
  useSalesTargetOptions: vi.fn(),
  useTargetProductSearch: () => productSearch,
  useCreateSalesTarget: () => create,
  usePatchSalesTarget: () => patchHeader,
  usePatchSalesTargetPeriod: () => patchPeriod,
  useCreateTargetChild: () => addChild,
}));
vi.mock('../hooks/useSalesTargets', () => hooks);

const duplicate = vi.hoisted(() => vi.fn());
const actionsOverride = vi.hoisted(() => ({ pending: null as React.ReactNode }));
vi.mock('../actions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../actions')>()),
  useSalesTargetActions: () => ({
    actions: [
      { key: 'sales_target.duplicate', label: 'Duplicate', run: duplicate },
      { key: 'sales_target.delete', label: 'Delete target', kind: 'destructive', run: vi.fn() },
    ],
    dialogs: null,
    pending: actionsOverride.pending,
  }),
}));

import TargetRecord, { additionalText, rateText } from './TargetRecord';

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/;
const PRODUCT_ID = '6f1c2d3e-4a5b-4c6d-8e9f-0a1b2c3d4e5f';

const OPTIONS = {
  agents: [
    { id: 'ali', code: 'ALI', label: 'ALI - Ali Hassan', team_id: 'north', team_name: 'North' },
  ],
  teams: [
    {
      id: 'north', name: 'North', is_active: true,
      members: [
        { sales_agent_id: 'ali', label: 'ALI - Ali Hassan', valid_from: null, valid_to: null },
        { sales_agent_id: 'mei', label: 'MEI - Tan Mei Ling', valid_from: null, valid_to: null },
      ],
    },
  ],
  categories: [{ id: 'cat1', label: 'BAS - Basins', parent_category_id: null }],
  brands: [
    { id: 'b1', label: 'MOC - Mocha' },
    { id: 'b2', label: 'TP - TP Enterprise' },
  ],
};

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 't1', target_no: 'TGT-000001', name: 'Ali Q4 basins', subject_kind: 'agent',
    sales_agent_id: 'ali', sales_team_id: null, subject_label: 'ALI - Ali Hassan',
    subject_team_name: 'North', parent: null, metric: 'amount', basis: 'ordered',
    product_scope: 'products', start_date: '2026-10-01', end_date: '2026-12-31',
    split_every: null, split_unit: null, counts_label: 'Ordered',
    scope: [{ id: PRODUCT_ID, kind: 'product', label: 'BSN-001 - Countertop basin' }],
    periods: [
      { id: 'p1', period_start: '2026-10-01', period_end: '2026-12-31', target_value: 1000, achieved_value: 500, achieved_pct: 50, is_current: true },
    ],
    children: [], members_without_figure: [], child_count: 0,
    commission_method: 'none', tiers: [],
    created_at: '2026-09-26T01:00:00', updated_at: '2026-09-26T01:00:00',
    ...over,
  };
}

function openTab(name: string) {
  const tab = screen.getByRole('tab', { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
}

function tabNames() {
  return screen.getAllByRole('tab').map((t) => t.textContent?.trim());
}

beforeEach(() => {
  actionsOverride.pending = null;
  router.push.mockReset();
  perms.granted = new Set(['sales.targets.view', 'sales.targets.add', 'sales.targets.edit', 'sales.targets.delete']);
  for (const m of [create, patchHeader, patchPeriod, addChild]) {
    m.mutateAsync.mockReset();
    m.mutateAsync.mockResolvedValue({ id: 'new1' });
  }
  hooks.useSalesTarget.mockReturnValue({ data: detail(), isLoading: false, isError: false });
  hooks.useSalesTargets.mockReturnValue({ data: { on: '2026-10-20', rows: [], unassigned_amount: 0, no_team_count: 0 } });
  hooks.useSalesTargetOptions.mockReturnValue({ data: OPTIONS });
  productSearch.mockResolvedValue([]);
  customerSearch.mockResolvedValue([]);
});

describe('TargetRecord: create (F4)', () => {
  it('opens as the record, empty, with the defaults, and no modal', () => {
    render(<TargetRecord preset={{ kind: 'agent' }} />);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('heading', { name: 'New target' })).toBeTruthy();
    expect(tabNames()).toEqual(['Details', 'Periods', 'Commission']);
    expect((screen.getByLabelText('Measure') as HTMLSelectElement).value).toBe('amount');
    expect((screen.getByLabelText('Counts') as HTMLSelectElement).value).toBe('invoiced');
    // TARGET-INVOICED: Invoiced leads the basis choices; saved targets keep their own.
    const counts = screen.getByLabelText('Counts') as HTMLSelectElement;
    expect(Array.from(counts.options).map((o) => o.textContent)).toEqual([
      'None', 'Invoiced', 'Ordered', 'Delivered',
    ]);
    expect((screen.getByLabelText('Applies to') as HTMLSelectElement).value).toBe('all');
    expect((screen.getByLabelText('Start date') as HTMLInputElement).value).toBe('2026-10-20');
    expect((screen.getByLabelText('End date') as HTMLInputElement).value).toBe('2026-10-31');
    expect((screen.getByRole('switch', { name: 'Split' }) as HTMLButtonElement).getAttribute('aria-checked')).toBe('false');
    // Cancel and Save sit in the header card, not a dialog footer.
    const header = screen.getByTestId('record-header');
    expect(within(header).getByRole('button', { name: 'Save' })).toBeTruthy();
    expect(within(header).getByRole('button', { name: 'Cancel' })).toBeTruthy();
  });

  it('saves an agent target and opens its record', async () => {
    render(<TargetRecord preset={{ kind: 'agent' }} />);
    fireEvent.change(screen.getByLabelText('Who'), { target: { value: 'ali' } });
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Ali Oct' } });
    fireEvent.change(screen.getByLabelText(/Target figure/), { target: { value: '5000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(create.mutateAsync).toHaveBeenCalledTimes(1));
    expect(create.mutateAsync).toHaveBeenCalledWith({
      subject_kind: 'agent', sales_agent_id: 'ali', target_value: 5000, name: 'Ali Oct',
      metric: 'amount', basis: 'invoiced', product_scope: 'all',
      start_date: '2026-10-20', end_date: '2026-10-31',
    });
    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/sales/targets/new1'));
  });

  it('a team target takes each agent figure on the Agents tab and shows their sum', async () => {
    render(<TargetRecord preset={{ kind: 'team', subjectId: 'north' }} />);
    expect(tabNames()).toEqual(['Details', 'Periods', 'Agents', 'Commission']);
    expect((screen.getByLabelText('Who') as HTMLSelectElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'North Oct' } });
    openTab('Agents');
    const agents = screen.getByRole('region', { name: 'Agents' });
    fireEvent.change(within(agents).getByLabelText('ALI - Ali Hassan figure'), { target: { value: '600' } });
    fireEvent.change(within(agents).getByLabelText('MEI - Tan Mei Ling figure'), { target: { value: '400' } });
    expect(within(agents).getByText('1,000')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(create.mutateAsync).toHaveBeenCalledTimes(1));
    expect(create.mutateAsync.mock.calls[0][0]).toMatchObject({
      subject_kind: 'team', sales_team_id: 'north',
      agent_figures: [
        { sales_agent_id: 'ali', target_value: 600 },
        { sales_agent_id: 'mei', target_value: 400 },
      ],
    });
  });

  it('Applies to offers Brand; picked brands show their names and are sent (F1)', async () => {
    render(<TargetRecord preset={{ kind: 'agent' }} />);
    const applies = screen.getByLabelText('Applies to') as HTMLSelectElement;
    expect(Array.from(applies.options).map((o) => o.textContent)).toEqual([
      'None', 'All products', 'Categories', 'Products', 'Brands',
    ]);
    fireEvent.change(applies, { target: { value: 'brands' } });
    fireEvent.click(screen.getByLabelText('MOC - Mocha'));
    expect(screen.getByTestId('chip').textContent).toBe('MOC - Mocha');
    fireEvent.change(screen.getByLabelText('Who'), { target: { value: 'ali' } });
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Ali Mocha' } });
    fireEvent.change(screen.getByLabelText(/Target figure/), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(create.mutateAsync).toHaveBeenCalledTimes(1));
    expect(create.mutateAsync.mock.calls[0][0]).toMatchObject({
      product_scope: 'brands', brand_ids: ['b1'],
    });
  });

  it('says what Split does in one line under the dates (F6)', () => {
    render(<TargetRecord preset={{ kind: 'agent' }} />);
    const dates = screen.getByRole('region', { name: 'Dates' });
    expect(
      within(dates).getByText(
        'Split breaks the dates into periods of N days, weeks or months, each with its own figure. Off: one figure for the whole range.',
      ),
    ).toBeTruthy();
  });

  it('cannot save a half-empty range, and says so in plain words (F6)', () => {
    render(<TargetRecord preset={{ kind: 'agent' }} />);
    fireEvent.change(screen.getByLabelText('Who'), { target: { value: 'ali' } });
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Ali Oct' } });
    fireEvent.change(screen.getByLabelText(/Target figure/), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '' } });
    expect(screen.getByText('Pick both a start date and an end date.')).toBeTruthy();
    const save = screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.click(save);
    expect(create.mutateAsync).not.toHaveBeenCalled();
  });
});

describe('TargetRecord: view and edit (F4, F5)', () => {
  it('heads the record, then tabs Details, Periods, Commission; Edit the primary, Duplicate in the gear', () => {
    render(<TargetRecord id="t1" />);
    const header = screen.getByTestId('record-header');
    expect(within(header).getByText('TGT-000001')).toBeTruthy();
    expect(within(header).getByRole('heading', { name: 'Ali Q4 basins' })).toBeTruthy();
    expect(tabNames()).toEqual(['Details', 'Periods', 'Commission']);
    const gear = screen.getByTestId('gear');
    expect(within(gear).getByRole('button', { name: 'Duplicate' })).toBeTruthy();
    expect(within(gear).queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(screen.getAllByRole('button', { name: 'Edit' })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
  });

  // TARGET-EDIT-CTA (owner, 5 Nov: "edit should be the CTA here").
  it('shows Edit as the primary button in the action group, outside the gear, and it opens edit mode', () => {
    render(<TargetRecord id="t1" />);
    const group = screen.getByTestId('detail-actions');
    const edit = within(group).getByRole('button', { name: 'Edit' });
    expect(screen.getByTestId('gear').contains(edit)).toBe(false);
    fireEvent.click(edit);
    expect(within(screen.getByTestId('record-header')).getByRole('button', { name: 'Save' })).toBeTruthy();
    expect(within(screen.getByTestId('record-header')).getByRole('button', { name: 'Cancel' })).toBeTruthy();
    expect(screen.getByLabelText('Name')).toBeTruthy();
  });

  it('gives the primary slot back to the delete countdown: no Edit while a delete is pending', () => {
    actionsOverride.pending = <span data-testid="countdown">Deleting</span>;
    render(<TargetRecord id="t1" />);
    expect(screen.getByTestId('countdown')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
  });

  it('shows the picked products by code and name in read mode, never an id (F5)', () => {
    render(<TargetRecord id="t1" />);
    const counts = screen.getByRole('region', { name: 'What counts' });
    expect(within(counts).getByText('BSN-001 - Countertop basin')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(UUID);
  });

  it('keeps the picked products named in edit mode, never an id (F5)', () => {
    render(<TargetRecord id="t1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(screen.getByTestId('chip').textContent).toBe('BSN-001 - Countertop basin');
    expect(document.body.textContent).not.toMatch(UUID);
  });

  it('edits in place in the same tabs and saves only what changed', async () => {
    render(<TargetRecord id="t1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(tabNames()).toEqual(['Details', 'Periods', 'Commission']);
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Ali Q4 all basins' } });
    fireEvent.change(screen.getByLabelText('Applies to'), { target: { value: 'brands' } });
    fireEvent.click(screen.getByLabelText('TP - TP Enterprise'));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patchHeader.mutateAsync).toHaveBeenCalledTimes(1));
    expect(patchHeader.mutateAsync).toHaveBeenCalledWith({
      targetId: 't1',
      name: 'Ali Q4 all basins',
      product_scope: 'brands',
      category_ids: [],
      product_ids: [],
      brand_ids: ['b2'],
    });
  });

  it('refuses to save an edit whose range lost an end, in plain words (F6)', () => {
    render(<TargetRecord id="t1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '' } });
    expect(screen.getByText('Pick both a start date and an end date.')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('offers no Edit without sales.targets.edit', () => {
    perms.granted = new Set(['sales.targets.view']);
    render(<TargetRecord id="t1" />);
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
  });
});

// ------------------------------------------------------------------------------------------
// Fix lane round 3 (the owner's retest of 27 Sep 14:25): figures are edited in Edit mode, no
// row pencils (F1); commission tiers in Edit mode (F2); the agent target record (F3).
// ------------------------------------------------------------------------------------------

const Q4_PERIODS = [
  { id: 'p1', period_start: '2026-10-01', period_end: '2026-10-31', target_value: 1000, achieved_value: 500, achieved_pct: 50, is_current: true, commission_earned: null, bonus_earned: null },
  { id: 'p2', period_start: '2026-11-01', period_end: '2026-11-30', target_value: 1000, achieved_value: 0, achieved_pct: 0, is_current: false, commission_earned: null, bonus_earned: null },
  { id: 'p3', period_start: '2026-12-01', period_end: '2026-12-31', target_value: 1000, achieved_value: 0, achieved_pct: 0, is_current: false, commission_earned: null, bonus_earned: null },
];

function splitAgent(over: Record<string, unknown> = {}) {
  return detail({ split_every: 1, split_unit: 'month', periods: Q4_PERIODS, ...over });
}

function teamTarget(over: Record<string, unknown> = {}) {
  return detail({
    id: 'team1', target_no: 'TGT-000003', name: '2026 Q4 Target', subject_kind: 'team',
    sales_agent_id: null, sales_team_id: 'north', subject_label: 'North', product_scope: 'all', scope: [],
    split_every: 1, split_unit: 'month',
    periods: Q4_PERIODS.map((p) => ({ ...p, id: `t${p.id}`, target_value: 1000 })),
    children: [
      {
        target_id: 'c1', target_no: 'TGT-000004', sales_agent_id: 'ali', label: 'ALI - Ali Hassan',
        periods: [
          { id: 'a1', period_start: '2026-10-01', target_value: 600 },
          { id: 'a2', period_start: '2026-11-01', target_value: 600 },
          { id: 'a3', period_start: '2026-12-01', target_value: 600 },
        ],
      },
      {
        target_id: 'c2', target_no: 'TGT-000005', sales_agent_id: 'cin', label: 'CIN - CONTACT W',
        periods: [
          { id: 'b1', period_start: '2026-10-01', target_value: 400 },
          { id: 'b2', period_start: '2026-11-01', target_value: 400 },
          { id: 'b3', period_start: '2026-12-01', target_value: 400 },
        ],
      },
    ],
    members_without_figure: [{ sales_agent_id: 'mei', label: 'MEI - Tan Mei Ling' }],
    child_count: 2,
    ...over,
  });
}

function openEdit() {
  fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
}

describe('TargetRecord round 3, F1: figures are edited in Edit mode', () => {
  it('Periods in read mode shows values only: no pencil, no input', () => {
    hooks.useSalesTarget.mockReturnValue({ data: splitAgent(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openTab('Periods');
    const periods = screen.getByRole('region', { name: 'Periods' });
    expect(within(periods).getByText('Current')).toBeTruthy();
    // The standard grid's own controls (Columns, sorting) only: no pencil.
    expect(within(periods).queryAllByRole('button', { name: /edit|pencil/i })).toHaveLength(0);
    expect(within(periods).queryAllByRole('spinbutton')).toHaveLength(0);
    expect(within(periods).getAllByText('1,000.00')).toHaveLength(3);
  });

  it('Periods in Edit mode takes a figure per period and Save sends every changed one in one request', async () => {
    hooks.useSalesTarget.mockReturnValue({ data: splitAgent(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openEdit();
    openTab('Periods');
    const periods = screen.getByRole('region', { name: 'Periods' });
    const inputs = within(periods).getAllByRole('spinbutton');
    expect(inputs).toHaveLength(3);
    fireEvent.change(inputs[0], { target: { value: '1500' } });
    fireEvent.change(inputs[2], { target: { value: '2500' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patchHeader.mutateAsync).toHaveBeenCalledTimes(1));
    expect(patchHeader.mutateAsync).toHaveBeenCalledWith({
      targetId: 't1',
      figures: [
        { period_id: 'p1', target_value: 1500 },
        { period_id: 'p3', target_value: 2500 },
      ],
    });
    expect(patchPeriod.mutateAsync).not.toHaveBeenCalled();
  });

  it('Cancel discards the typed figures', () => {
    hooks.useSalesTarget.mockReturnValue({ data: splitAgent(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openEdit();
    openTab('Periods');
    fireEvent.change(within(screen.getByRole('region', { name: 'Periods' })).getAllByRole('spinbutton')[1], {
      target: { value: '9' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    const periods = screen.getByRole('region', { name: 'Periods' });
    expect(within(periods).queryAllByRole('spinbutton')).toHaveLength(0);
    expect(within(periods).getAllByText('1,000.00')).toHaveLength(3);
    expect(patchHeader.mutateAsync).not.toHaveBeenCalled();
  });

  it('no row pencil anywhere, in read or Edit mode', () => {
    hooks.useSalesTarget.mockReturnValue({ data: teamTarget(), isLoading: false, isError: false });
    render(<TargetRecord id="team1" />);
    const pencil = /edit (period )?figure|edit figure for/i;
    for (const tab of ['Periods', 'Agents']) {
      openTab(tab);
      expect(screen.queryAllByRole('button', { name: pencil })).toHaveLength(0);
    }
    openEdit();
    for (const tab of ['Periods', 'Agents']) {
      openTab(tab);
      expect(screen.queryAllByRole('button', { name: pencil })).toHaveLength(0);
    }
  });

  it('Agents in read mode: each agent per period, the team total, no buttons', () => {
    hooks.useSalesTarget.mockReturnValue({ data: teamTarget(), isLoading: false, isError: false });
    render(<TargetRecord id="team1" />);
    openTab('Agents');
    const agents = screen.getByRole('region', { name: 'Agents' });
    expect(within(agents).getByRole('link', { name: 'ALI - Ali Hassan' })).toBeTruthy();
    expect(within(agents).getAllByText('600')).toHaveLength(3);
    expect(within(agents).getByText('No figure yet')).toBeTruthy();
    expect(within(agents).getByText('Team target')).toBeTruthy();
    expect(within(agents).queryAllByRole('button')).toHaveLength(0);
    expect(within(agents).queryAllByRole('spinbutton')).toHaveLength(0);
  });

  it('Agents in Edit mode: an input per agent per period, the team total per period live, one Save', async () => {
    hooks.useSalesTarget.mockReturnValue({ data: teamTarget(), isLoading: false, isError: false });
    render(<TargetRecord id="team1" />);
    openEdit();
    openTab('Agents');
    const agents = screen.getByRole('region', { name: 'Agents' });
    // Three agents (one with no figure yet) by three months.
    expect(within(agents).getAllByRole('spinbutton')).toHaveLength(9);
    fireEvent.change(within(agents).getByLabelText('ALI - Ali Hassan, 01/11/2026'), { target: { value: '900' } });
    fireEvent.change(within(agents).getByLabelText('MEI - Tan Mei Ling, 01/12/2026'), { target: { value: '50' } });
    const totals = within(agents).getByTestId('team-totals');
    // Oct 1,000; Nov 900 + 400; Dec 1,000 + 50.
    expect(within(totals).getByText('1,000')).toBeTruthy();
    expect(within(totals).getByText('1,300')).toBeTruthy();
    expect(within(totals).getByText('1,050')).toBeTruthy();

    openTab('Periods');
    const periods = screen.getByRole('region', { name: 'Periods' });
    expect(within(periods).queryAllByRole('spinbutton')).toHaveLength(0);
    expect(within(periods).getByText('1,300')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patchHeader.mutateAsync).toHaveBeenCalledTimes(1));
    expect(patchHeader.mutateAsync).toHaveBeenCalledWith({
      targetId: 'team1',
      figures: [{ period_id: 'a2', target_value: 900 }],
      new_agents: [
        {
          sales_agent_id: 'mei',
          figures: [{ period_start: '2026-12-01', target_value: 50 }],
        },
      ],
    });
    expect(addChild.mutateAsync).not.toHaveBeenCalled();
  });
});

describe('TargetRecord round 3, F2: commission tiers in Edit mode only', () => {
  it('read mode with no tiers: "No commission" and Add tier opens Edit mode with a tier row', () => {
    render(<TargetRecord id="t1" />);
    openTab('Commission');
    let commission = screen.getByRole('region', { name: 'Commission' });
    expect(within(commission).getByText('No commission')).toBeTruthy();
    expect(within(commission).queryAllByRole('spinbutton')).toHaveLength(0);
    fireEvent.click(within(commission).getByRole('button', { name: 'Add tier' }));
    commission = screen.getByRole('region', { name: 'Commission' });
    expect(within(commission).getByLabelText('Tier 1 from %')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy();
  });

  it('adds tiers in Edit mode and saves them with how they pay', async () => {
    render(<TargetRecord id="t1" />);
    openEdit();
    openTab('Commission');
    const commission = screen.getByRole('region', { name: 'Commission' });
    fireEvent.click(within(commission).getByRole('button', { name: 'Add tier' }));
    fireEvent.change(within(commission).getByLabelText('Tier 1 from %'), { target: { value: '0' } });
    fireEvent.change(within(commission).getByLabelText('Tier 1 rate (% of RM)'), { target: { value: '2' } });
    fireEvent.click(within(commission).getByRole('button', { name: 'Add tier' }));
    fireEvent.change(within(commission).getByLabelText('Tier 2 from %'), { target: { value: '100' } });
    fireEvent.change(within(commission).getByLabelText('Tier 2 rate (% of RM)'), { target: { value: '4' } });
    // The RM Additional is the tier's Bonus (lane TARGET-TIER-ADDITIONAL).
    fireEvent.change(within(commission).getByLabelText('Tier 2 additional'), { target: { value: '500' } });
    fireEvent.change(within(commission).getByLabelText('Tier 2 additional in'), { target: { value: 'amount' } });
    expect((within(commission).getByLabelText('How tiers pay') as HTMLSelectElement).value).toBe('marginal');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patchHeader.mutateAsync).toHaveBeenCalledTimes(1));
    expect(patchHeader.mutateAsync).toHaveBeenCalledWith({
      targetId: 't1',
      commission_method: 'marginal',
      tiers: [
        { from_pct: 0, rate: 2, bonus_amount: null },
        { from_pct: 100, rate: 4, bonus_amount: 500 },
      ],
    });
  });

  it('read mode shows saved tiers as rows, no inputs; Edit mode removes one', async () => {
    hooks.useSalesTarget.mockReturnValue({
      data: detail({
        commission_method: 'marginal',
        tiers: [
          { from_pct: 0, rate: 2, bonus_amount: null },
          { from_pct: 100, rate: 4, bonus_amount: 500 },
        ],
      }),
      isLoading: false, isError: false,
    });
    render(<TargetRecord id="t1" />);
    openTab('Commission');
    let commission = screen.getByRole('region', { name: 'Commission' });
    expect(within(commission).getByText('Higher rate above each threshold only')).toBeTruthy();
    expect(within(commission).getByText('100%')).toBeTruthy();
    expect(within(commission).queryAllByRole('spinbutton')).toHaveLength(0);
    expect(within(commission).queryByRole('button', { name: /remove tier/i })).toBeNull();
    openEdit();
    commission = screen.getByRole('region', { name: 'Commission' });
    fireEvent.click(within(commission).getByRole('button', { name: 'Remove tier 2' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patchHeader.mutateAsync).toHaveBeenCalledTimes(1));
    expect(patchHeader.mutateAsync).toHaveBeenCalledWith({
      targetId: 't1',
      commission_method: 'marginal',
      tiers: [{ from_pct: 0, rate: 2, bonus_amount: null }],
    });
  });

  it('removing every tier turns the commission off', async () => {
    hooks.useSalesTarget.mockReturnValue({
      data: detail({ commission_method: 'retroactive', tiers: [{ from_pct: 0, rate: 2, bonus_amount: null }] }),
      isLoading: false, isError: false,
    });
    render(<TargetRecord id="t1" />);
    openEdit();
    openTab('Commission');
    fireEvent.click(screen.getByRole('button', { name: 'Remove tier 1' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patchHeader.mutateAsync).toHaveBeenCalledTimes(1));
    expect(patchHeader.mutateAsync).toHaveBeenCalledWith({ targetId: 't1', commission_method: 'none', tiers: [] });
  });

  it('without sales.targets.edit there is no Add tier', () => {
    perms.granted = new Set(['sales.targets.view']);
    render(<TargetRecord id="t1" />);
    openTab('Commission');
    const commission = screen.getByRole('region', { name: 'Commission' });
    expect(within(commission).getByText('No commission')).toBeTruthy();
    expect(within(commission).queryByRole('button', { name: /add tier/i })).toBeNull();
  });
});

describe('TargetRecord round 3, F3: the agent target record', () => {
  const PARENT = teamTarget();
  function childRecord() {
    return splitAgent({
      id: 'c2', target_no: 'TGT-000005', name: '2026 Q4 Target', sales_agent_id: 'cin',
      subject_label: 'CIN - CONTACT W', product_scope: 'all', scope: [],
      parent: { id: 'team1', name: '2026 Q4 Target', target_no: 'TGT-000003' },
      periods: Q4_PERIODS.map((p) => ({ ...p, id: `b${p.id.slice(1)}`, target_value: 400 })),
    });
  }
  beforeEach(() => {
    hooks.useSalesTarget.mockImplementation((id: string | null) => ({
      data: id === 'team1' ? PARENT : id === 'c2' ? childRecord() : undefined,
      isLoading: false,
      isError: false,
    }));
  });

  it('heads the record "Agent target, part of" its team target, with a link', () => {
    render(<TargetRecord id="c2" />);
    const header = screen.getByTestId('record-header');
    expect(within(header).getByText(/Agent target, part of/)).toBeTruthy();
    expect(within(header).getByRole('link', { name: '2026 Q4 Target' }).getAttribute('href')).toBe('/sales/targets/team1');
    expect(tabNames()).toEqual(['Details', 'Periods', 'Team target', 'Commission']);
  });

  it('the Team target tab shows the parent: name, what counts, dates, split, periods, and opens it', () => {
    render(<TargetRecord id="c2" />);
    openTab('Team target');
    const team = screen.getByRole('region', { name: 'Team target' });
    expect(within(team).getByText('2026 Q4 Target')).toBeTruthy();
    expect(within(team).getByText('TGT-000003')).toBeTruthy();
    expect(within(team).getByText('Amount (RM)')).toBeTruthy();
    expect(within(team).getByText('Ordered')).toBeTruthy();
    expect(within(team).getByText('All products')).toBeTruthy();
    expect(within(team).getByText('01/10/2026 - 31/12/2026')).toBeTruthy();
    expect(within(team).getByText('Every month')).toBeTruthy();
    expect(within(team).getAllByText('1,000')).toHaveLength(3);
    expect(within(team).getByRole('link', { name: 'Open team target' }).getAttribute('href')).toBe('/sales/targets/team1');
  });

  it('inherited fields stay read-only in Edit mode with one "Set on the team target" line', () => {
    render(<TargetRecord id="c2" />);
    expect(screen.queryByText(/Set on 2026 Q4 Target/)).toBeNull();
    openEdit();
    expect(screen.queryByLabelText('Measure')).toBeNull();
    expect(screen.queryByLabelText('Applies to')).toBeNull();
    expect(screen.queryByLabelText('Start date')).toBeNull();
    expect(screen.queryByRole('switch', { name: 'Split' })).toBeNull();
    expect(screen.getAllByText('Set on the team target')).toHaveLength(1);
    expect(screen.queryByText(/Set on 2026 Q4 Target/)).toBeNull();
  });

  it("edits the agent's own figures per period in Edit mode and saves them in one request", async () => {
    render(<TargetRecord id="c2" />);
    openEdit();
    openTab('Periods');
    const inputs = within(screen.getByRole('region', { name: 'Periods' })).getAllByRole('spinbutton');
    expect(inputs).toHaveLength(3);
    fireEvent.change(inputs[1], { target: { value: '800' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patchHeader.mutateAsync).toHaveBeenCalledTimes(1));
    expect(patchHeader.mutateAsync).toHaveBeenCalledWith({
      targetId: 'c2',
      figures: [{ period_id: 'b2', target_value: 800 }],
    });
  });
});


// ----------------------------------------------------------------------------------------
// Lane SALES-TARGET-DEALER: dealer subject and the one engine's Commission settings (UAC D4-2)
// ----------------------------------------------------------------------------------------

const A1 = 'c-a1';
const A3 = 'c-a3';

function dealerDetail(over: Record<string, unknown> = {}) {
  return detail({
    subject_kind: 'dealer', sales_agent_id: null, subject_label: 'Dealer A Sdn Bhd',
    subject_team_name: null, product_scope: 'all', scope: [],
    start_date: '2026-01-01', end_date: '2026-12-31', split_every: 3, split_unit: 'month',
    periods: [
      {
        id: 'q2', period_start: '2026-04-01', period_end: '2026-06-30', target_value: 200000,
        achieved_value: 250000, achieved_pct: 125, is_current: true, commission_earned: 5400,
        bonus_earned: 0, accounts: [
          { customer_id: A1, code: '300-A0123', name: 'DEALER A SDN BHD', label: 'A/C I', achieved_value: 180000 },
          { customer_id: A3, code: '300-A0124', name: 'DEALER A SDN BHD (III)', label: 'A/C III', achieved_value: 70000 },
        ],
      },
    ],
    commission_method: 'retroactive', threshold_unit: 'amount', rounding: 'sen', tiers_per_period: true,
    tiers: [
      { from_pct: null, threshold: 200000, rate: null, bonus_amount: null, is_additional: false,
        period_start: '2026-04-01', account_rates: [{ customer_id: A1, rate: 2 }] },
      { from_pct: null, threshold: 250000, rate: null, bonus_amount: null, is_additional: false,
        period_start: '2026-04-01', account_rates: [{ customer_id: A1, rate: 3 }] },
    ],
    accounts: [
      { customer_id: A1, code: '300-A0123', name: 'DEALER A SDN BHD', label: 'A/C I' },
      { customer_id: A3, code: '300-A0124', name: 'DEALER A SDN BHD (III)', label: 'A/C III' },
    ],
    payout_account: { customer_id: A1, code: '300-A0123', name: 'DEALER A SDN BHD', label: 'A/C I' },
    ...over,
  });
}

describe('TargetRecord: dealer targets (lane SALES-TARGET-DEALER)', () => {
  it('a dealer target has an Accounts tab with each account and the account it pays to', () => {
    hooks.useSalesTarget.mockReturnValue({ data: dealerDetail(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    expect(tabNames()).toEqual(['Details', 'Periods', 'Accounts', 'Commission']);
    openTab('Accounts');
    const table = screen.getByRole('group', { name: 'Counted accounts' });
    expect(within(table).getByText('300-A0124')).toBeTruthy();
    expect(within(table).getByText('A/C III')).toBeTruthy();
    expect(within(table).getByText('70,000.00')).toBeTruthy();
    expect(screen.getAllByText('300-A0123 - DEALER A SDN BHD (A/C I)').length).toBeGreaterThan(0);
    expect(within(table).getByText(/sales orders, incl\. tax/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(UUID);
  });

  it('an account target its dealer target replaces names it, and a replaced period says so', () => {
    const base = dealerDetail();
    hooks.useSalesTarget.mockReturnValue({
      data: dealerDetail({
        replaced_by: { target_id: 'dealer-1', target_no: 'TGT-000009', name: 'Dealer A 2026 yearly' },
        periods: base.periods.map((p: { id: string }) => ({ ...p, commission_earned: 0, replaced: p.id === 'q2' })),
      }),
      isLoading: false,
      isError: false,
    });
    render(<TargetRecord id="t1" />);
    openTab('Accounts');
    expect(screen.getByRole('link', { name: 'TGT-000009 Dealer A 2026 yearly' })).toBeTruthy();
    openTab('Periods');
    expect(screen.getByText('Replaced by TGT-000009')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(UUID);
  });

  it('Periods labels the SO-based figures of an Ordered dealer target marked as sales orders incl. tax', () => {
    hooks.useSalesTarget.mockReturnValue({ data: dealerDetail(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openTab('Periods');
    expect(screen.getByText('Achieved (sales orders, incl. tax)')).toBeTruthy();
  });

  it('read mode Details shows the same Accounts as Edit: code and name, one per line (owner, 4 Nov)', () => {
    hooks.useSalesTarget.mockReturnValue({ data: dealerDetail(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    const list = screen.getByRole('list', { name: 'Accounts' });
    expect(within(list).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      '300-A0123 - DEALER A SDN BHD',
      '300-A0124 - DEALER A SDN BHD (III)',
    ]);
    // The field is labelled Accounts in read mode too, never "Dealer".
    expect(screen.queryByText('Dealer', { selector: 'span.text-xs' })).toBeNull();
    expect(document.body.textContent).not.toMatch(UUID);
  });

  it('an Invoiced dealer target is the billing figure: never marked provisional (TARGET-INVOICED)', () => {
    hooks.useSalesTarget.mockReturnValue({
      data: dealerDetail({ basis: 'invoiced', counts_label: 'Invoiced' }),
      isLoading: false,
      isError: false,
    });
    render(<TargetRecord id="t1" />);
    expect(screen.getByText('Invoiced')).toBeTruthy();
    openTab('Periods');
    expect(screen.queryByText(/incl\. tax/)).toBeNull();
    expect(screen.getByText('Achieved')).toBeTruthy();
    openTab('Accounts');
    expect(screen.queryByText(/incl\. tax/)).toBeNull();
    expect(screen.getByText('Sales (RM)')).toBeTruthy();
  });

  it('the Commission tab shows the four settings and a rate column per account', () => {
    hooks.useSalesTarget.mockReturnValue({ data: dealerDetail(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openTab('Commission');
    expect(screen.getByText('Highest rate on everything')).toBeTruthy();
    expect(screen.getByText('Own tiers per period')).toBeTruthy();
    expect(screen.getByText('Sen (0.01)')).toBeTruthy();
    const table = screen.getByRole('group', { name: 'Commission tiers' });
    expect(within(table).getByText('A/C I rate')).toBeTruthy();
    expect(within(table).getByText('A/C III rate')).toBeTruthy();
    // A/C III has no rate on these tiers: it earns nothing on them (ruling 2).
    expect(within(table).getAllByText('-').length).toBeGreaterThanOrEqual(2);
  });

  it('creates a dealer target with accounts, RM tiers per period and an additional line', async () => {
    customerSearch.mockResolvedValue([{ value: A1, label: '300-A0123 - DEALER A SDN BHD' }]);
    render(<TargetRecord preset={{ kind: 'dealer' }} />);
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Dealer A 2026 quarterly' } });
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-01-01' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-03-31' } });
    // The multi-select mock lists only `options`; the dealer picker searches, so seed by hand.
    expect(screen.getByRole('group', { name: 'Accounts' })).toBeTruthy();
    openTab('Commission');
    expect((screen.getByLabelText('Threshold in') as HTMLSelectElement).value).toBe('amount');
    expect((screen.getByRole('switch', { name: 'Own tiers per period' })).getAttribute('aria-checked')).toBe('true');
    // Saving without an account is not possible.
    expect((within(screen.getByTestId('record-header')).getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('TargetRecord: the one engine on an agent target', () => {
  it('an agent target offers Threshold in, Round to and own tiers per period, and sends them', async () => {
    render(<TargetRecord id="t1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    openTab('Commission');
    fireEvent.click(screen.getByRole('button', { name: /Add tier/ }));
    fireEvent.change(screen.getByLabelText('Threshold in'), { target: { value: 'amount' } });
    fireEvent.change(screen.getByLabelText('Round to'), { target: { value: 'ringgit' } });
    fireEvent.change(screen.getByLabelText(/Tier 1 from \(rm\)/i), { target: { value: '500000' } });
    fireEvent.change(screen.getByLabelText(/Tier 1 rate/), { target: { value: '1.5' } });
    // No "+ Additional" row type any more: the tier carries its own Additional (owner, 5 Nov).
    expect(screen.queryByLabelText('Tier 1 type')).toBeNull();
    fireEvent.change(screen.getByLabelText('Tier 1 additional'), { target: { value: '0.5' } });
    fireEvent.click(within(screen.getByTestId('record-header')).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patchHeader.mutateAsync).toHaveBeenCalled());
    const sent = patchHeader.mutateAsync.mock.calls[0][0];
    expect(sent.threshold_unit).toBe('amount');
    expect(sent.rounding).toBe('ringgit');
    expect(sent.tiers).toEqual([
      { threshold: 500000, rate: 1.5, bonus_amount: null, additional_rate: 0.5 },
    ]);
  });
});


// ----------------------------------------------------------------------------------------
// Lane TARGET-COMMISSION-VIEW: what the target earned, per period, and where it pays
// ----------------------------------------------------------------------------------------

/** TGT-000008 in miniature (the owner's 4 Nov case): Q1 + Q2 paid, Q3 none, Q4 current. */
function tgt8(over: Record<string, unknown> = {}) {
  const account = { customer_id: A1, code: '300-A077', name: 'A CRAFT IDEA SDN BHD', label: 'A/C I' };
  const period = (id: string, start: string, end: string, achieved: number, pct: number, paid: number, tier: number | null, rate: number | null, current = false) => ({
    id, period_start: start, period_end: end, target_value: 60000, achieved_value: achieved, achieved_pct: pct,
    is_current: current, commission_earned: paid, bonus_earned: 0, tier_reached: tier,
    tier_rates: rate === null ? [] : [{ label: null, rate }],
    accounts: [{ ...account, achieved_value: achieved }],
  });
  return dealerDetail({
    periods: [
      period('q1', '2026-01-01', '2026-03-31', 61351.64, 102.3, 3681.1, 1, 6),
      period('q2', '2026-04-01', '2026-06-30', 64740.4, 107.9, 3237.02, 1, 5),
      period('q3', '2026-07-01', '2026-09-30', 23460, 39.1, 0, null, null),
      period('q4', '2026-10-01', '2026-12-31', 1235.58, 2.1, 0, null, null, true),
    ],
    accounts: [account],
    payout_account: account,
    commission_to_date: 6918.12,
    commission_current: 0,
    ...over,
  });
}

describe('TargetRecord: commission view (lane TARGET-COMMISSION-VIEW)', () => {
  it('shows what the target earned to date, the current period apart, and the account it pays to', () => {
    hooks.useSalesTarget.mockReturnValue({ data: tgt8(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    const summary = screen.getByRole('region', { name: 'Commission summary' });
    expect(within(summary).getByText('6,918.12')).toBeTruthy();
    // Owner markup 5 Nov 11:40: the period's dates only, no subtexts.
    expect(within(summary).getByText('Current period commission (RM)')).toBeTruthy();
    expect(within(summary).getByText('01/10/2026 - 31/12/2026')).toBeTruthy();
    expect(within(summary).getByText('300-A077 - A CRAFT IDEA SDN BHD (A/C I)')).toBeTruthy();
    expect(within(summary).queryByText(/not final/)).toBeNull();
    expect(within(summary).queryByText('Periods that have ended')).toBeNull();
    expect(within(summary).queryByText('Payment is not tracked in the CRM')).toBeNull();
    expect(within(summary).queryByText('Current period so far (RM)')).toBeNull();
  });

  it('Periods shows the tier reached, its rate, the commission in RM with 2 decimals, where it pays and a total', () => {
    hooks.useSalesTarget.mockReturnValue({ data: tgt8(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openTab('Periods');
    const q1 = screen.getByText('01/01/2026 - 31/03/2026').closest('tr') as HTMLElement;
    expect(within(q1).getByText('Tier 1')).toBeTruthy();
    expect(within(q1).getByText('6.00%')).toBeTruthy();
    expect(within(q1).getByText('3,681.10')).toBeTruthy();
    // The cell names the code and account; the full name is its title and in the summary.
    expect(within(q1).getByText('300-A077 (A/C I)').getAttribute('title')).toBe('300-A077 - A CRAFT IDEA SDN BHD (A/C I)');
    expect(within(q1).getByText('61,351.64')).toBeTruthy();
    const q3 = screen.getByText('01/07/2026 - 30/09/2026').closest('tr') as HTMLElement;
    expect(within(q3).getByText('None')).toBeTruthy();
    expect(within(q3).getAllByText('-').length).toBeGreaterThan(0);
    const total = screen.getByText('Total').closest('tr') as HTMLElement;
    expect(within(total).getByText('6,918.12')).toBeTruthy();
    expect(within(total).getByText('240,000.00')).toBeTruthy();
  });

  it('Accounts shows every period, its total, the commission and where it pays, not only the current one', () => {
    hooks.useSalesTarget.mockReturnValue({ data: tgt8(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openTab('Accounts');
    const table = screen.getByRole('group', { name: 'Counted accounts' });
    expect(within(table).getByText('Sales (RM, sales orders, incl. tax)')).toBeTruthy();
    for (const label of ['01/01/2026 - 31/03/2026', '01/04/2026 - 30/06/2026', '01/07/2026 - 30/09/2026', '01/10/2026 - 31/12/2026']) {
      expect(within(table).getByText(label)).toBeTruthy();
    }
    expect(within(table).getAllByText('3,681.10')).toHaveLength(1);
    expect(within(table).getByText('Period total (so far)')).toBeTruthy();
    // Q4's 1,235.58 now sits on its own period row, not under an ambiguous column header.
    const current = within(table).getByText('Period total (so far)').closest('tr') as HTMLElement;
    expect(within(current).getByText('1,235.58')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(UUID);
  });

  it('a target with no commission shows no summary', () => {
    hooks.useSalesTarget.mockReturnValue({
      data: tgt8({ commission_method: 'none', commission_to_date: null, commission_current: null }),
      isLoading: false,
      isError: false,
    });
    render(<TargetRecord id="t1" />);
    expect(screen.queryByRole('region', { name: 'Commission summary' })).toBeNull();
  });
});

describe('rateText', () => {
  it('formats one rate, per-account rates and a quantity rate', () => {
    expect(rateText([{ label: null, rate: 6 }], 'amount')).toBe('6.00%');
    expect(rateText([{ label: 'A/C I', rate: 2 }, { label: 'A/C III', rate: 3.5 }], 'amount')).toBe('A/C I 2.00%, A/C III 3.50%');
    expect(rateText([{ label: null, rate: 1.5 }], 'quantity')).toBe('RM 1.50/unit');
    expect(rateText([], 'amount')).toBe('');
  });
});

// ----------------------------------------------------------------------------------------
// Lane TARGET-TIER-ADDITIONAL: a tier's Additional sits on the tier (owner, 5 Nov)
// ----------------------------------------------------------------------------------------

describe('TargetRecord: tier Additional (lane TARGET-TIER-ADDITIONAL)', () => {
  /** A CRAFT IDEA A/C I, 2026 Q1: tier 2 (75,000) at 6% + 1% on 76,793.92. */
  function aCraft() {
    const base = tgt8();
    const q1 = {
      ...base.periods[0],
      achieved_value: 76793.92,
      achieved_pct: 128,
      tier_reached: 2,
      commission_earned: 5375.58,
      tier_rates: [{ label: 'A/C I', rate: 6 }],
      tier_additional: { kind: 'pct', value: 1 },
    };
    return {
      ...base,
      commission_method: 'retroactive',
      threshold_unit: 'amount',
      tiers_per_period: true,
      periods: [q1, ...base.periods.slice(1)],
      tiers: [
        { threshold: 60000, rate: 5, bonus_amount: null, additional_rate: 1, period_start: '2026-01-01' },
        { threshold: 75000, rate: 6, bonus_amount: null, additional_rate: 1, period_start: '2026-01-01' },
        { threshold: 85000, rate: 7, bonus_amount: 250, additional_rate: null, period_start: '2026-01-01' },
      ],
    };
  }

  it('Periods shows the reached tier rate plus its Additional: A/C I 6.00% + 1.00%', () => {
    hooks.useSalesTarget.mockReturnValue({ data: aCraft(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openTab('Periods');
    const q1 = screen.getByText('01/01/2026 - 31/03/2026').closest('tr') as HTMLElement;
    expect(within(q1).getByText('A/C I 6.00% + 1.00%')).toBeTruthy();
    expect(within(q1).getByText('5,375.58')).toBeTruthy();
  });

  it('the Commission tab shows each tier with its Additional, % or RM, and no "+ Additional" rows', () => {
    hooks.useSalesTarget.mockReturnValue({ data: aCraft(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openTab('Commission');
    const commission = screen.getByRole('region', { name: 'Commission' });
    expect(within(commission).getAllByText('+ 1.00%')).toHaveLength(2);
    expect(within(commission).getByText('+ RM 250.00')).toBeTruthy();
    expect(within(commission).queryByText(/\+ Additional from/)).toBeNull();
  });

  it('Edit reads a % Additional back into the tier and saves it unchanged', async () => {
    hooks.useSalesTarget.mockReturnValue({ data: aCraft(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openEdit();
    openTab('Commission');
    expect((screen.getByLabelText('Tier 2 additional') as HTMLInputElement).value).toBe('1');
    expect((screen.getByLabelText('Tier 3 additional in') as HTMLSelectElement).value).toBe('amount');
    fireEvent.change(screen.getByLabelText('Tier 2 additional'), { target: { value: '1.5' } });
    fireEvent.click(within(screen.getByTestId('record-header')).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patchHeader.mutateAsync).toHaveBeenCalled());
    const sent = patchHeader.mutateAsync.mock.calls[0][0];
    expect(sent.tiers.map((t: { additional_rate?: number; bonus_amount: number | null }) => [t.additional_rate, t.bonus_amount])).toEqual([
      [1, null], [1.5, null], [undefined, 250],
    ]);
  });
});

describe('additionalText', () => {
  it('formats a % Additional, an RM Additional and a quantity Additional', () => {
    expect(additionalText({ kind: 'pct', value: 1 }, 'amount')).toBe('+ 1.00%');
    expect(additionalText({ kind: 'amount', value: 500 }, 'amount')).toBe('+ RM 500.00');
    expect(additionalText({ kind: 'pct', value: 0.5 }, 'quantity')).toBe('+ RM 0.50/unit');
    expect(additionalText(null, 'amount')).toBe('');
  });
});

// ----------------------------------------------------------------------------------------
// Owner 5 Nov 11:30: the standard grid, a Period filter on the tiers, tiers in a lightbox
// ----------------------------------------------------------------------------------------

describe('TargetRecord: standard grids and the tier lightbox (lane TARGET-TIER-ADDITIONAL)', () => {
  /** TGT-000009-shaped: Q1 tiers 85,000 / 115,000 / 135,000 at 3 / 4 / 5 %, Q2 other figures. */
  function bathIdea() {
    const base = tgt8();
    const tier = (start: string, threshold: number, rate: number, add: number | null = null) => ({
      threshold, rate, bonus_amount: null, additional_rate: add, period_start: start,
    });
    return {
      ...base,
      commission_method: 'retroactive',
      threshold_unit: 'amount',
      tiers_per_period: true,
      periods: [{ ...base.periods[0], tier_reached: 2, tier_rates: [{ label: 'A/C I', rate: 4 }], tier_additional: { kind: 'pct', value: 1 } }, ...base.periods.slice(1)],
      tiers: [
        tier('2026-01-01', 85000, 3), tier('2026-01-01', 115000, 4, 1), tier('2026-01-01', 135000, 5),
        tier('2026-04-01', 90000, 3), tier('2026-04-01', 120000, 4),
      ],
    };
  }

  it('Periods, Accounts and Commission each offer the Columns chooser', () => {
    hooks.useSalesTarget.mockReturnValue({ data: bathIdea(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    for (const tab of ['Periods', 'Accounts', 'Commission']) {
      openTab(tab);
      const panel = screen.getByRole('region', { name: tab });
      expect(within(panel).getByRole('button', { name: 'Columns' })).toBeTruthy();
    }
  });

  it('the Commission Period filter shows only the picked periods’ tiers', () => {
    hooks.useSalesTarget.mockReturnValue({ data: bathIdea(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openTab('Commission');
    const tiers = screen.getByRole('group', { name: 'Commission tiers' });
    expect(within(tiers).getByText('90,000')).toBeTruthy();
    const filter = screen.getByRole('group', { name: 'Period' });
    fireEvent.click(within(filter).getByLabelText('01/01/2026 - 31/03/2026'));
    expect(within(tiers).getByText('85,000')).toBeTruthy();
    expect(within(tiers).getByText('115,000')).toBeTruthy();
    expect(within(tiers).getByText('135,000')).toBeTruthy();
    expect(within(tiers).queryByText('90,000')).toBeNull();
  });

  it('Tier reached on Periods opens that period’s tiers with the reached tier marked', async () => {
    hooks.useSalesTarget.mockReturnValue({ data: bathIdea(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openTab('Periods');
    const q1 = screen.getByText('01/01/2026 - 31/03/2026').closest('tr') as HTMLElement;
    fireEvent.click(within(q1).getByRole('button', { name: 'Tier 2' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Tiers, 01/01/2026 - 31/03/2026')).toBeTruthy();
    expect(within(dialog).getByText('Tier 2 reached: A/C I 4.00% + 1.00%')).toBeTruthy();
    const reached = within(dialog).getByText('115,000').closest('tr') as HTMLElement;
    expect(reached.getAttribute('data-reached')).toBe('true');
    expect(within(dialog).queryByText('90,000')).toBeNull();
  });

  it('a period on the Accounts tab opens the same lightbox', async () => {
    hooks.useSalesTarget.mockReturnValue({ data: bathIdea(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openTab('Accounts');
    const accounts = screen.getByRole('group', { name: 'Counted accounts' });
    fireEvent.click(within(accounts).getByRole('button', { name: '01/01/2026 - 31/03/2026' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Tiers, 01/01/2026 - 31/03/2026')).toBeTruthy();
  });
});

describe('TargetRecord: owner markup 5 Nov 11:40 (lane TARGET-TIER-ADDITIONAL)', () => {
  it('a dealer target has no "For" subtitle and Details shows the Customer, not the target name', () => {
    hooks.useSalesTarget.mockReturnValue({ data: tgt8({ subject_label: 'BEAUFORT HOMES SDN BHD', name: 'BEAUFORT HOMES SDN BHD 2026 quarterly' }), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    expect(screen.queryByText(/^For /)).toBeNull();
    expect(screen.getByText('Customer')).toBeTruthy();
    const customer = screen.getByText('Customer').parentElement as HTMLElement;
    expect(within(customer).getByText('BEAUFORT HOMES SDN BHD')).toBeTruthy();
    expect(within(customer).queryByText('BEAUFORT HOMES SDN BHD 2026 quarterly')).toBeNull();
  });
});

describe('TargetRecord: crew browser pass on 1104 (lane TARGET-TIER-ADDITIONAL)', () => {
  /** TGT-000008 as imported: one account, every tier's rate held per account (target_tier_rates). */
  function imported() {
    const base = tgt8();
    const tier = (threshold: number, rate: number, start: string, add: number | null = null) => ({
      threshold, rate: null, bonus_amount: null, additional_rate: add, is_additional: false,
      period_start: start, account_rates: [{ customer_id: A1, rate }],
    });
    return {
      ...base,
      commission_method: 'retroactive',
      threshold_unit: 'amount',
      tiers_per_period: true,
      tiers: [
        tier(60000, 5, '2026-01-01'), tier(75000, 6, '2026-01-01'),
        tier(60000, 5, '2026-04-01'), tier(75000, 6, '2026-04-01'),
      ],
    };
  }

  it('Save keeps each tier’s per-account rate; it does not collapse them into the tier rate', async () => {
    hooks.useSalesTarget.mockReturnValue({ data: imported(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openEdit();
    openTab('Commission');
    fireEvent.change(screen.getByLabelText('Tier 1 additional'), { target: { value: '1' } });
    fireEvent.click(within(screen.getByTestId('record-header')).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patchHeader.mutateAsync).toHaveBeenCalled());
    const sent = patchHeader.mutateAsync.mock.calls[0][0];
    expect(sent.tiers.map((t: { account_rates: unknown }) => t.account_rates)).toEqual([
      [{ customer_id: A1, rate: 5 }], [{ customer_id: A1, rate: 6 }],
      [{ customer_id: A1, rate: 5 }], [{ customer_id: A1, rate: 6 }],
    ]);
    expect(sent.tiers[0].additional_rate).toBe(1);
  });

  it('a tier saved with one rate for every account still saves as one rate', async () => {
    const data = imported();
    data.tiers = data.tiers.map((t) => ({ ...t, rate: t.account_rates[0].rate, account_rates: null })) as never;
    hooks.useSalesTarget.mockReturnValue({ data, isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openEdit();
    openTab('Commission');
    fireEvent.change(screen.getByLabelText('Tier 1 additional'), { target: { value: '1' } });
    fireEvent.click(within(screen.getByTestId('record-header')).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patchHeader.mutateAsync).toHaveBeenCalled());
    const sent = patchHeader.mutateAsync.mock.calls[0][0];
    expect(sent.tiers.map((t: { rate: number; account_rates: unknown }) => [t.rate, t.account_rates])).toEqual([
      [5, null], [6, null], [5, null], [6, null],
    ]);
  });

  it('Pays to names the account label once when the account name already carries it', () => {
    const account = { customer_id: A1, code: '300-A077', name: 'A CRAFT IDEA SDN BHD (A/C I)', label: 'A/C I' };
    hooks.useSalesTarget.mockReturnValue({ data: tgt8({ payout_account: account }), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    const summary = screen.getByRole('region', { name: 'Commission summary' });
    expect(within(summary).getByText('300-A077 - A CRAFT IDEA SDN BHD (A/C I)')).toBeTruthy();
    expect(document.body.textContent).not.toContain('(A/C I) (A/C I)');
  });

  it('Pays to names the label once when the account name carries it in square brackets (1104)', () => {
    const account = { customer_id: A1, code: '300-A077', name: 'A CRAFT IDEA SDN BHD [A/C I]', label: 'A/C I' };
    hooks.useSalesTarget.mockReturnValue({ data: tgt8({ payout_account: account }), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    const summary = screen.getByRole('region', { name: 'Commission summary' });
    expect(within(summary).getByText('300-A077 - A CRAFT IDEA SDN BHD [A/C I]')).toBeTruthy();
    expect(document.body.textContent).not.toContain('[A/C I] (A/C I)');
  });

  it('the Commission Period filter keeps its pick through Edit and Cancel', () => {
    hooks.useSalesTarget.mockReturnValue({ data: imported(), isLoading: false, isError: false });
    render(<TargetRecord id="t1" />);
    openTab('Commission');
    let filter = screen.getByRole('group', { name: 'Period' });
    fireEvent.click(within(filter).getByLabelText('01/01/2026 - 31/03/2026'));
    openEdit();
    fireEvent.click(within(screen.getByTestId('record-header')).getByRole('button', { name: 'Cancel' }));
    filter = screen.getByRole('group', { name: 'Period' });
    expect((within(filter).getByLabelText('01/01/2026 - 31/03/2026') as HTMLInputElement).checked).toBe(true);
  });
});
