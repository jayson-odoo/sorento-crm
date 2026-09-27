/**
 * The target record, `/sales/targets/{id}` and `/sales/targets/new` (UAC S1-18, S1-23 to
 * S1-28; the S1 hand test of 27 Sep, F1, F4, F5, F6).
 *
 * ONE record view for create, view and edit, no modal: a header card, then line tabs in the
 * order Details, Periods, Agents (a team target only), Commission. Create opens the same view
 * empty with the defaults Amount, Ordered, All products, today to month end, split off. Edit is
 * an item in the gear dropdown. Every pick is the system SearchableSelect or
 * SearchableMultiSelect, and a picked category, product or brand always shows its name.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

const router = vi.hoisted(() => ({ push: vi.fn() }));
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
  }) => (
    <select
      id={props.id}
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
const hooks = vi.hoisted(() => ({
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
vi.mock('../actions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../actions')>()),
  useSalesTargetActions: () => ({
    actions: [
      { key: 'sales_target.duplicate', label: 'Duplicate', run: duplicate },
      { key: 'sales_target.delete', label: 'Delete target', kind: 'destructive', run: vi.fn() },
    ],
    dialogs: null,
    pending: null,
  }),
}));

import TargetRecord from './TargetRecord';

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
});

describe('TargetRecord: create (F4)', () => {
  it('opens as the record, empty, with the defaults, and no modal', () => {
    render(<TargetRecord preset={{ kind: 'agent' }} />);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('heading', { name: 'New target' })).toBeTruthy();
    expect(tabNames()).toEqual(['Details', 'Periods', 'Commission']);
    expect((screen.getByLabelText('Measure') as HTMLSelectElement).value).toBe('amount');
    expect((screen.getByLabelText('Counts') as HTMLSelectElement).value).toBe('ordered');
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
      metric: 'amount', basis: 'ordered', product_scope: 'all',
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
  it('heads the record, then tabs Details, Periods, Commission; Edit and Duplicate in the gear', () => {
    render(<TargetRecord id="t1" />);
    const header = screen.getByTestId('record-header');
    expect(within(header).getByText('TGT-000001')).toBeTruthy();
    expect(within(header).getByRole('heading', { name: 'Ali Q4 basins' })).toBeTruthy();
    expect(tabNames()).toEqual(['Details', 'Periods', 'Commission']);
    const gear = screen.getByTestId('gear');
    expect(within(gear).getByRole('button', { name: 'Edit' })).toBeTruthy();
    expect(within(gear).getByRole('button', { name: 'Duplicate' })).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'Edit' })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
  });

  it('shows the picked products by code and name in read mode, never an id (F5)', () => {
    render(<TargetRecord id="t1" />);
    const counts = screen.getByRole('region', { name: 'What counts' });
    expect(within(counts).getByText('BSN-001 - Countertop basin')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(UUID);
  });

  it('keeps the picked products named in edit mode, never an id (F5)', () => {
    render(<TargetRecord id="t1" />);
    fireEvent.click(within(screen.getByTestId('gear')).getByRole('button', { name: 'Edit' }));
    expect(screen.getByTestId('chip').textContent).toBe('BSN-001 - Countertop basin');
    expect(document.body.textContent).not.toMatch(UUID);
  });

  it('edits in place in the same tabs and saves only what changed', async () => {
    render(<TargetRecord id="t1" />);
    fireEvent.click(within(screen.getByTestId('gear')).getByRole('button', { name: 'Edit' }));
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
    fireEvent.click(within(screen.getByTestId('gear')).getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '' } });
    expect(screen.getByText('Pick both a start date and an end date.')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("marks today's period and edits its figure in place on Periods", async () => {
    render(<TargetRecord id="t1" />);
    openTab('Periods');
    const periods = screen.getByRole('region', { name: 'Periods' });
    expect(within(periods).getByText('Current')).toBeTruthy();
    fireEvent.click(within(periods).getByRole('button', { name: /edit period figure/i }));
    fireEvent.change(within(periods).getByLabelText(/new value/), { target: { value: '1200' } });
    fireEvent.click(within(periods).getByRole('button', { name: 'Save figure' }));
    await waitFor(() =>
      expect(patchPeriod.mutateAsync).toHaveBeenCalledWith({ targetId: 't1', periodId: 'p1', target_value: 1200 }),
    );
  });

  it('a team target has read-only periods and an Agents tab with Add figure (S1-27, S1-28)', () => {
    hooks.useSalesTarget.mockReturnValue({
      data: detail({
        subject_kind: 'team', sales_agent_id: null, sales_team_id: 'north', subject_label: 'North',
        product_scope: 'all', scope: [],
        children: [{ target_id: 'c1', sales_agent_id: 'ali', label: 'ALI - Ali Hassan', periods: [{ id: 'cp1', period_start: '2026-10-01', target_value: 600 }] }],
        members_without_figure: [{ sales_agent_id: 'mei', label: 'MEI - Tan Mei Ling' }],
        child_count: 1,
      }),
      isLoading: false, isError: false,
    });
    render(<TargetRecord id="t1" />);
    expect(tabNames()).toEqual(['Details', 'Periods', 'Agents', 'Commission']);
    openTab('Periods');
    const periods = screen.getByRole('region', { name: 'Periods' });
    expect(within(periods).queryByRole('button', { name: /edit period/i })).toBeNull();
    openTab('Agents');
    const agents = screen.getByRole('region', { name: 'Agents' });
    expect(within(agents).getByText('ALI - Ali Hassan')).toBeTruthy();
    expect(within(agents).getByRole('button', { name: /add figure/i })).toBeTruthy();
  });

  it('a child target names its parent and keeps What counts read-only in edit', () => {
    hooks.useSalesTarget.mockReturnValue({
      data: detail({ parent: { id: 'p0', name: 'North Team Target', target_no: 'TGT-000009' } }),
      isLoading: false, isError: false,
    });
    render(<TargetRecord id="t1" />);
    expect(screen.getAllByText('North Team Target').length).toBeGreaterThan(0);
    fireEvent.click(within(screen.getByTestId('gear')).getByRole('button', { name: 'Edit' }));
    expect(screen.queryByLabelText('Applies to')).toBeNull();
    expect(screen.getByText(/set on north team target/i)).toBeTruthy();
  });

  it('shows "No commission" with Add tier, disabled, before S4', () => {
    render(<TargetRecord id="t1" />);
    openTab('Commission');
    const commission = screen.getByRole('region', { name: 'Commission' });
    expect(within(commission).getByText('No commission')).toBeTruthy();
    expect((within(commission).getByRole('button', { name: /add tier/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('offers no Edit without sales.targets.edit', () => {
    perms.granted = new Set(['sales.targets.view']);
    render(<TargetRecord id="t1" />);
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
  });
});
