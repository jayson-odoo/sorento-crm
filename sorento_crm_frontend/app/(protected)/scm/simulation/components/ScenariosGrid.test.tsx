import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

// Same reason every other grid test mocks this: the grid renders no rows until the
// listing personalization hook is mocked, because it fetches through react-query.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

import { ScenariosGrid } from './ScenariosGrid';
import type { ScenarioRow } from '../types/simulation.types';

function row(over: Partial<ScenarioRow> = {}): ScenarioRow {
  return {
    code: 'SIM-P001',
    title: 'Steady high demand, low stock',
    segment: 'dealer',
    policy: 'forecast',
    expected_note: 'net (100) well below ROP (740) -> triggered buy.',
    inputs: { on_hand: 100, committed: 0, spo_incoming: 0, po_open: 0, demand_label: 'SO' },
    current: {
      rec_type: 'buy',
      recommended_qty: 1240,
      rounded_qty: 1240,
      triggered_reason: 'net_below_rop',
      cash_impact: 74400,
    },
    baseline: {
      rec_type: 'buy',
      recommended_qty: 1240,
      rounded_qty: 1240,
      triggered_reason: 'net_below_rop',
      cash_impact: 74400,
    },
    status: 'SAME',
    changed_groups: [],
    ...over,
  };
}

const noop = () => {};

describe('ScenariosGrid - loading', () => {
  it('renders a skeleton', () => {
    render(
      <ScenariosGrid
        rows={[]}
        isLoading
        isError={false}
        error={null}
        onRetry={noop}
        onSelectRow={noop}
      />,
    );
    expect(screen.getByTestId('scenarios-grid-loading')).toBeTruthy();
  });
});

describe('ScenariosGrid - error', () => {
  it('renders the error message and a retry button', () => {
    const onRetry = vi.fn();
    render(
      <ScenariosGrid
        rows={[]}
        isLoading={false}
        isError
        error={new Error('backend unreachable')}
        onRetry={onRetry}
        onSelectRow={noop}
      />,
    );
    expect(screen.getByText('backend unreachable')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalled();
  });
});

describe('ScenariosGrid - empty', () => {
  it('renders an empty state when the registry itself is empty', () => {
    render(
      <ScenariosGrid
        rows={[]}
        isLoading={false}
        isError={false}
        error={null}
        onRetry={noop}
        onSelectRow={noop}
      />,
    );
    expect(screen.getByText(/no scenarios are registered/i)).toBeTruthy();
  });
});

describe('ScenariosGrid - data', () => {
  it('renders a SAME row and calls onSelectRow when clicked', () => {
    const onSelectRow = vi.fn();
    render(
      <ScenariosGrid
        rows={[row()]}
        isLoading={false}
        isError={false}
        error={null}
        onRetry={noop}
        onSelectRow={onSelectRow}
      />,
    );
    const table = within(screen.getByRole('table'));
    expect(table.getByText('SIM-P001')).toBeTruthy();
    expect(table.getByText('Steady high demand, low stock')).toBeTruthy();
    expect(table.getByText('Same')).toBeTruthy();

    fireEvent.click(table.getByText('SIM-P001'));
    expect(onSelectRow).toHaveBeenCalledWith('SIM-P001');
  });
});

describe('ScenariosGrid - input columns', () => {
  it('renders on hand, demand (with the SO label) and 0 for absent SPO/PO - never a dash', () => {
    render(
      <ScenariosGrid
        rows={[row({ inputs: { on_hand: 100, committed: 0, spo_incoming: 0, po_open: 0, demand_label: 'SO' } })]}
        isLoading={false}
        isError={false}
        error={null}
        onRetry={noop}
        onSelectRow={noop}
      />,
    );
    const table = within(screen.getByRole('table'));
    // "100" (on hand) and three separate "0"s (committed/SPO/PO) - all real zeros, not
    // an em-dash placeholder, since the absence of supply is itself information.
    expect(table.getByText('100')).toBeTruthy();
    expect(table.getAllByText('0').length).toBeGreaterThanOrEqual(3);
    expect(table.getByText('SO')).toBeTruthy();
  });

  it('labels a project-segment scenario\'s demand as OI (Order Inquiry)', () => {
    render(
      <ScenariosGrid
        rows={[
          row({
            segment: 'project',
            inputs: { on_hand: 300, committed: 40, spo_incoming: null, po_open: 0, demand_label: 'OI' },
          }),
        ]}
        isLoading={false}
        isError={false}
        error={null}
        onRetry={noop}
        onSelectRow={noop}
      />,
    );
    const table = within(screen.getByRole('table'));
    expect(table.getByText('40')).toBeTruthy();
    expect(table.getByText('OI')).toBeTruthy();
  });
});

describe('ScenariosGrid - changed row', () => {
  it('shows the baseline value beside the current one and the changed groups as tags', () => {
    render(
      <ScenariosGrid
        rows={[
          row({
            status: 'CHANGED',
            changed_groups: ['quantity suggestion', 'cover composition'],
            current: {
              rec_type: 'buy',
              recommended_qty: 1240,
              rounded_qty: 1240,
              triggered_reason: 'net_below_rop',
              cash_impact: 74400,
            },
            baseline: {
              rec_type: 'buy',
              recommended_qty: 1000,
              rounded_qty: 1000,
              triggered_reason: 'net_below_rop',
              cash_impact: 60000,
            },
          }),
        ]}
        isLoading={false}
        isError={false}
        error={null}
        onRetry={noop}
        onSelectRow={noop}
      />,
    );
    const table = within(screen.getByRole('table'));
    expect(table.getByText('Changed')).toBeTruthy();
    expect(table.getByText('(was 1,000)')).toBeTruthy();
    expect(table.getByText('quantity suggestion')).toBeTruthy();
    expect(table.getByText('cover composition')).toBeTruthy();
  });

  it('renders "None" and an em-dash placeholder for a scenario with no recommendation', () => {
    render(
      <ScenariosGrid
        rows={[row({ current: null, status: 'NO_BASELINE', baseline: null, changed_groups: [] })]}
        isLoading={false}
        isError={false}
        error={null}
        onRetry={noop}
        onSelectRow={noop}
      />,
    );
    const table = within(screen.getByRole('table'));
    expect(table.getByText('None')).toBeTruthy();
    expect(table.getByText('No baseline')).toBeTruthy();
  });
});

describe('ScenariosGrid - the sort arrow sorts (BL-027 / AC-G01)', () => {
  /** The scenario code of every rendered row, top to bottom. */
  function codeOrder(): string[] {
    return Array.from(document.querySelectorAll('tbody tr')).map(
      (tr) => tr.querySelector('td')?.textContent?.trim() ?? '',
    );
  }

  function threeQuantities() {
    const qty = (n: number) => ({
      rec_type: 'buy',
      recommended_qty: n,
      rounded_qty: n,
      triggered_reason: 'net_below_rop',
      cash_impact: n,
    });
    render(
      <ScenariosGrid
        rows={[
          row({ code: 'AAA-9', current: qty(9), baseline: qty(9) }),
          row({ code: 'BBB-10', current: qty(10), baseline: qty(10) }),
          row({ code: 'CCC-2', current: qty(2), baseline: qty(2) }),
        ]}
        isLoading={false}
        isError={false}
        error={null}
        onRetry={noop}
        onSelectRow={noop}
      />,
    );
  }

  it('reorders on the recommended quantity numerically (9 before 10)', () => {
    threeQuantities();
    expect(codeOrder()).toEqual(['AAA-9', 'BBB-10', 'CCC-2']);

    fireEvent.click(screen.getByRole('button', { name: 'Qty' }));

    expect(codeOrder()).toEqual(['CCC-2', 'AAA-9', 'BBB-10']);
  });

  it('reverses on the second click', () => {
    threeQuantities();

    fireEvent.click(screen.getByRole('button', { name: 'Qty' }));
    fireEvent.click(screen.getByRole('button', { name: 'Qty' }));

    expect(codeOrder()).toEqual(['BBB-10', 'AAA-9', 'CCC-2']);
  });
});
