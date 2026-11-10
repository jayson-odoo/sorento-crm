/**
 * Costing Settings dialog (lane PRODUCT-COSTING, Phase 2 red tests F3; UAC AC-CG-13, AC-ER-01..03,
 * AC-ST-01, AC-ST-02, AC-CG-10). Three line tabs: Exchange rates, SST and method, Transport by category.
 *
 * ASSUMED NAMES (the coder implements exactly these; CONTRACT section 5):
 *  - `./CostingSettingsDialog` exports `CostingSettingsDialog` (a default export is also accepted)
 *    with props `{ open: boolean; onOpenChange: (open: boolean) => void }`.
 *  - Service calls: getExchangeRates(), createExchangeRate(body), updateExchangeRate(id, body),
 *    getCostingSettings(), saveCostingSettings(body), getCategoryRules(), saveCategoryRule(categoryId, body).
 *  - Exchange rates tab: table headers Currency, Effective from, "Units per MYR 1", "MYR per unit",
 *    Status, Note; Status text "Scheduled" / "In force" / "Past"; dates as "dd/mm/yyyy".
 *    The add form is always visible with: text input "Currency", native date input "Effective from",
 *    radios "Units per MYR 1" (checked by default) and "MYR per unit", number input "Rate",
 *    text input "Note", and a submit button "Add rate". The body carries `units_per_base` for the
 *    first basis and `rate_to_base` for the second, never both; `note` only when typed.
 *    The Add rate form needs `scm.config.manage`; without it no form is rendered.
 *  - Each rate row has a delete button (accessible name matches /delete|remove/i) that parks the
 *    deferred action actionKey 'exchange_rate.delete', entityType 'exchange_rate', entityId = rate id
 *    through createPendingAction (no confirm dialog).
 *  - SST and method tab: number input "SST factor", select "Default cost method" (option values
 *    primary / average / last_po only), button "Save" -> saveCostingSettings({ sst_factor, default_method }).
 *    sst_factor <= 0 sends nothing. Needs `products.party_costing.manage` to see Save.
 *  - Transport by category tab: per category a select `Transport mode for {category_name}` (values
 *    add / multiply, empty = no rule) and a number input `Transport value for {category_name}`, button
 *    "Save" -> saveCategoryRule(category_id, { mode, value }) only for changed categories; clearing
 *    both sends { mode: null, value: null }.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string; value: string; onChange: (v: string) => void;
    options?: { value: string; label: string }[]; placeholder?: string; disabled?: boolean;
    'aria-label'?: string;
  }) => (
    <select id={props.id} aria-label={props['aria-label']} value={props.value} disabled={props.disabled}
      onChange={(e) => props.onChange(e.target.value)}>
      <option value="">{props.placeholder ?? ''}</option>
      {(props.options ?? []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}));

const perms = vi.hoisted(() => ({ granted: new Set<string>() }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => perms.granted.has(slug),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast }));

const createPendingAction = vi.hoisted(() => vi.fn());
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

const service = vi.hoisted(() => ({
  getExchangeRates: vi.fn(),
  createExchangeRate: vi.fn(),
  updateExchangeRate: vi.fn(),
  getCostingSettings: vi.fn(),
  saveCostingSettings: vi.fn(),
  getCategoryRules: vi.fn(),
  saveCategoryRule: vi.fn(),
}));
vi.mock('../services/costingService', () => service);

import * as dialogModule from './CostingSettingsDialog';
const CostingSettingsDialog = ((dialogModule as Record<string, unknown>).CostingSettingsDialog ??
  (dialogModule as Record<string, unknown>).default) as React.ComponentType<{
  open: boolean;
  onOpenChange: (open: boolean) => void;
}>;

const RATES = {
  data: [
    { id: 'r3', currency: 'RMB', rate_to_base: 0.613497, units_per_base: 1.63, effective_from: '2026-12-01', note: 'Q4 budget', status: 'scheduled' },
    { id: 'r2', currency: 'RMB', rate_to_base: 0.625, units_per_base: 1.6, effective_from: '2026-11-01', note: 'Workbook rate', status: 'in_force' },
    { id: 'r1', currency: 'RMB', rate_to_base: 0.617284, units_per_base: 1.62, effective_from: '2026-09-01', note: null, status: 'past' },
    { id: 'u1', currency: 'USD', rate_to_base: 4.4, units_per_base: 0.2273, effective_from: '2026-11-01', note: null, status: 'in_force' },
  ],
};

function mount(onOpenChange = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <CostingSettingsDialog open onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
  return onOpenChange;
}
function openTab(name: string) {
  const tab = screen.getByRole('tab', { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
}
const type = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

beforeEach(() => {
  vi.clearAllMocks();
  perms.granted = new Set(['products.cost.view', 'products.party_costing.manage', 'scm.config.manage']);
  service.getExchangeRates.mockResolvedValue(RATES);
  service.createExchangeRate.mockResolvedValue({ id: 'new' });
  service.updateExchangeRate.mockResolvedValue({ id: 'r2' });
  service.getCostingSettings.mockResolvedValue({ sst_factor: 1.1, default_method: 'primary' });
  service.saveCostingSettings.mockResolvedValue({ sst_factor: 1.12, default_method: 'average' });
  service.getCategoryRules.mockResolvedValue({
    data: [
      { category_id: 'cat-ceramics', category_name: 'Ceramics', mode: 'add', value: 8 },
      { category_id: 'cat-taps', category_name: 'Taps', mode: 'multiply', value: 1.07 },
      { category_id: 'cat-acc', category_name: 'Accessories', mode: null, value: null },
    ],
  });
  service.saveCategoryRule.mockResolvedValue({});
  createPendingAction.mockResolvedValue({
    id: 'pa-1', action_key: 'exchange_rate.delete', entity_type: 'exchange_rate', entity_id: 'r2',
    commit_at: '2099-01-01T00:00:10', window_seconds: 10,
  });
});

describe('tabs (AC-CG-13)', () => {
  it('has three line tabs in order, opening on Exchange rates', async () => {
    mount();
    const tabs = (await screen.findAllByRole('tab')).map((t) => t.textContent?.trim());
    expect(tabs).toEqual(['Exchange rates', 'SST and method', 'Transport by category']);
    expect(screen.getByRole('tab', { name: 'Exchange rates' }).getAttribute('aria-selected')).toBe('true');
  });
});

describe('Exchange rates tab (AC-ER-01..03)', () => {
  it('lists dated rates with the workbook units-per-MYR figure and a status each', async () => {
    mount();
    expect(await screen.findByText('Workbook rate')).toBeTruthy();
    for (const h of ['Currency', 'Effective from', 'Units per MYR 1', 'MYR per unit', 'Status', 'Note']) {
      expect(screen.getAllByText(h).length).toBeGreaterThan(0);
    }
    const inForce = screen.getByText('Workbook rate').closest('tr') as HTMLElement;
    expect(within(inForce).getByText(/01\/11\/2026/)).toBeTruthy();
    expect(within(inForce).getByText(/^1\.6(0*)$/)).toBeTruthy();
    expect(within(inForce).getByText('In force')).toBeTruthy();
    const scheduled = screen.getByText('Q4 budget').closest('tr') as HTMLElement;
    expect(within(scheduled).getByText('Scheduled')).toBeTruthy();
    expect(within(scheduled).getByText(/01\/12\/2026/)).toBeTruthy();
    expect(screen.getAllByText('Past').length).toBeGreaterThan(0);
  });

  it('adds a rate typed as Units per MYR 1 (the default) and sends units_per_base only', async () => {
    mount();
    await screen.findByText('Workbook rate');
    expect((screen.getByRole('radio', { name: 'Units per MYR 1' }) as HTMLInputElement).checked).toBe(true);
    type('Currency', 'RMB');
    type('Effective from', '2026-12-15');
    type('Rate', '1.65');
    fireEvent.click(screen.getByRole('button', { name: 'Add rate' }));
    await waitFor(() => expect(service.createExchangeRate).toHaveBeenCalledTimes(1));
    const body = service.createExchangeRate.mock.calls[0][0];
    expect(body).toMatchObject({ currency: 'RMB', effective_from: '2026-12-15', units_per_base: 1.65 });
    expect(body).not.toHaveProperty('rate_to_base');
  });

  it('adds a rate typed as MYR per unit and sends rate_to_base only', async () => {
    mount();
    await screen.findByText('Workbook rate');
    fireEvent.click(screen.getByRole('radio', { name: 'MYR per unit' }));
    type('Currency', 'USD');
    type('Effective from', '2026-12-15');
    type('Rate', '4.5');
    type('Note', 'Dec');
    fireEvent.click(screen.getByRole('button', { name: 'Add rate' }));
    await waitFor(() => expect(service.createExchangeRate).toHaveBeenCalledTimes(1));
    const body = service.createExchangeRate.mock.calls[0][0];
    expect(body).toMatchObject({ currency: 'USD', effective_from: '2026-12-15', rate_to_base: 4.5, note: 'Dec' });
    expect(body).not.toHaveProperty('units_per_base');
  });

  it('refuses a zero rate before calling the server', async () => {
    mount();
    await screen.findByText('Workbook rate');
    type('Currency', 'RMB');
    type('Effective from', '2026-12-15');
    type('Rate', '0');
    fireEvent.click(screen.getByRole('button', { name: 'Add rate' }));
    await new Promise((r) => setTimeout(r, 30));
    expect(service.createExchangeRate).not.toHaveBeenCalled();
  });

  it('shows the server message when the same currency and date already exist (409)', async () => {
    service.createExchangeRate.mockRejectedValue(new Error('A rate for RMB on 2026-11-01 already exists'));
    mount();
    await screen.findByText('Workbook rate');
    type('Currency', 'RMB');
    type('Effective from', '2026-11-01');
    type('Rate', '1.6');
    fireEvent.click(screen.getByRole('button', { name: 'Add rate' }));
    await waitFor(() =>
      expect(toast.error.mock.calls.length > 0 || screen.queryByText(/already exists/) !== null).toBe(true),
    );
  });

  it('parks a rate deletion as a deferred action with no confirm dialog', async () => {
    mount();
    const row = (await screen.findByText('Workbook rate')).closest('tr') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: /delete|remove/i }));
    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({ actionKey: 'exchange_rate.delete', entityType: 'exchange_rate', entityId: 'r2' }),
      ),
    );
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('hides the add form and delete buttons without scm.config.manage', async () => {
    perms.granted = new Set(['products.cost.view', 'products.party_costing.manage']);
    mount();
    await screen.findByText('Workbook rate');
    expect(screen.queryByRole('button', { name: 'Add rate' })).toBeNull();
    expect(screen.queryByLabelText('Currency')).toBeNull();
    const row = screen.getByText('Workbook rate').closest('tr') as HTMLElement;
    expect(within(row).queryByRole('button', { name: /delete|remove/i })).toBeNull();
  });

  it('shows an empty list without crashing', async () => {
    service.getExchangeRates.mockResolvedValue({ data: [] });
    mount();
    await screen.findByRole('tab', { name: 'Exchange rates' });
    await waitFor(() => expect(service.getExchangeRates).toHaveBeenCalled());
    expect(screen.queryByText('Workbook rate')).toBeNull();
  });
});

describe('SST and method tab (AC-ST-01)', () => {
  it('loads the company SST factor and default method', async () => {
    mount();
    openTab('SST and method');
    await waitFor(() => expect((screen.getByLabelText('SST factor') as HTMLInputElement).value).toBe('1.1'));
    const method = screen.getByLabelText('Default cost method') as HTMLSelectElement;
    expect(method.value).toBe('primary');
    expect(Array.from(method.options).map((o) => o.value).filter(Boolean).sort()).toEqual(['average', 'last_po', 'primary']);
  });

  it('saves both values together', async () => {
    mount();
    openTab('SST and method');
    await waitFor(() => expect((screen.getByLabelText('SST factor') as HTMLInputElement).value).toBe('1.1'));
    type('SST factor', '1.12');
    type('Default cost method', 'average');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(service.saveCostingSettings).toHaveBeenCalledTimes(1));
    expect(service.saveCostingSettings).toHaveBeenCalledWith({ sst_factor: 1.12, default_method: 'average' });
  });

  it('will not send a zero or negative SST factor', async () => {
    mount();
    openTab('SST and method');
    await waitFor(() => expect((screen.getByLabelText('SST factor') as HTMLInputElement).value).toBe('1.1'));
    type('SST factor', '0');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await new Promise((r) => setTimeout(r, 30));
    expect(service.saveCostingSettings).not.toHaveBeenCalled();
  });

  it('has no Save without products.party_costing.manage', async () => {
    perms.granted = new Set(['products.cost.view']);
    mount();
    openTab('SST and method');
    await screen.findByLabelText('SST factor');
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
  });
});

describe('Transport by category tab (AC-ST-02)', () => {
  it('lists every category with its rule, blank when it has none', async () => {
    mount();
    openTab('Transport by category');
    expect(await screen.findByLabelText('Transport mode for Ceramics')).toBeTruthy();
    expect((screen.getByLabelText('Transport mode for Ceramics') as HTMLSelectElement).value).toBe('add');
    expect((screen.getByLabelText('Transport value for Ceramics') as HTMLInputElement).value).toBe('8');
    expect((screen.getByLabelText('Transport mode for Taps') as HTMLSelectElement).value).toBe('multiply');
    expect((screen.getByLabelText('Transport value for Taps') as HTMLInputElement).value).toBe('1.07');
    expect((screen.getByLabelText('Transport mode for Accessories') as HTMLSelectElement).value).toBe('');
    expect((screen.getByLabelText('Transport value for Accessories') as HTMLInputElement).value).toBe('');
  });

  it('saves only the category that changed', async () => {
    mount();
    openTab('Transport by category');
    await screen.findByLabelText('Transport mode for Ceramics');
    type('Transport value for Ceramics', '9');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(service.saveCategoryRule).toHaveBeenCalledTimes(1));
    expect(service.saveCategoryRule).toHaveBeenCalledWith('cat-ceramics', { mode: 'add', value: 9 });
  });

  it('sets a rule on a category that had none', async () => {
    mount();
    openTab('Transport by category');
    await screen.findByLabelText('Transport mode for Accessories');
    type('Transport mode for Accessories', 'multiply');
    type('Transport value for Accessories', '1.07');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(service.saveCategoryRule).toHaveBeenCalledTimes(1));
    expect(service.saveCategoryRule).toHaveBeenCalledWith('cat-acc', { mode: 'multiply', value: 1.07 });
  });

  it('clearing the mode and the value removes the rule', async () => {
    mount();
    openTab('Transport by category');
    await screen.findByLabelText('Transport mode for Taps');
    type('Transport mode for Taps', '');
    type('Transport value for Taps', '');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(service.saveCategoryRule).toHaveBeenCalledTimes(1));
    expect(service.saveCategoryRule).toHaveBeenCalledWith('cat-taps', { mode: null, value: null });
  });

  it('has no Save without products.party_costing.manage', async () => {
    perms.granted = new Set(['products.cost.view']);
    mount();
    openTab('Transport by category');
    await screen.findByLabelText('Transport mode for Ceramics');
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
  });
});
