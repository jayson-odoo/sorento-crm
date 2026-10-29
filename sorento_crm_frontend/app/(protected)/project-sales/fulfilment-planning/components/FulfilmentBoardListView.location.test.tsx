/**
 * PLAN-SO-LOCATION (`documentation/plans/project-sales/PLAN-so-location-29oct.md`): the List
 * view names each SO line's own location in a column of its own, right after Product, so a
 * row whose suggestion is a Buy (which names no warehouse) still says where the line is.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { BoardContribution } from '../../_shared/types/fulfilmentPlanning.types';

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
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/lib/toast', () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), error: vi.fn() }),
}));

import { FulfilmentBoardListView } from './FulfilmentBoardListView';

function contribution(overrides: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: 'so-1:line-80',
    sales_order_id: 'so-1',
    line_id: 'core-line-80',
    product_id: 'prod-1',
    so_number: 'SO428264',
    customer_name: 'Customer A',
    agent_code: 'AGENT1',
    agent_label: 'Agent One',
    project_label: 'Project A',
    line_no: 80,
    so_line_no: overrides.line_no ?? 80,
    item_code: 'SRTWT7445-LV',
    qty: '42',
    qty_outstanding: '42',
    required_date: '2026-11-04',
    fulfilment_location: 'BRW-BB',
    unplannable: false,
    rank_score: 0.5,
    rank_factors: [],
    sources: [{ kind: 'buy', qty: '42', reason: 'Nothing free at any location.' }],
    trail: [],
    item_flags: null,
    contested: false,
    covered: false,
    decision: null,
    ...overrides,
  };
}

function renderView(rows: BoardContribution[]) {
  return render(
    <FulfilmentBoardListView
      contributions={rows}
      draft={{}}
      onDecide={vi.fn()}
      onDecideMany={vi.fn(async () => ({ saved: 0, failed: 0 }))}
      onDecideBatch={vi.fn(async () => ({ savedKeys: [], failed: [] }))}
    />,
  );
}

function rowOf(soNumber: string): HTMLElement {
  return screen.getByText(soNumber).closest('tr') as HTMLElement;
}

/** The filter's own Location trigger, not the column header of the same name. */
async function locationFilterTrigger(): Promise<HTMLElement> {
  return screen.findByRole('combobox', { name: 'Location' });
}

const threeLines = [
  contribution({ key: 'so-1:line-1', so_number: 'SO000001', line_no: 1, fulfilment_location: 'WH3-BB' }),
  contribution({ key: 'so-2:line-2', so_number: 'SO000002', line_no: 2 }),
  contribution({ key: 'so-3:line-3', so_number: 'SO000003', line_no: 3, fulfilment_location: 'DC1-BB' }),
];

describe('PLAN-SO-LOCATION: the List view names the SO line’s own location', () => {
  it('has a Location column right after Product', async () => {
    renderView([contribution()]);
    await screen.findByText('SO428264');
    const headers = screen
      .getAllByRole('columnheader')
      .map((header) => header.textContent?.trim() ?? '');
    const product = headers.indexOf('Product');
    expect(product).toBeGreaterThan(-1);
    expect(headers[product + 1]).toBe('Location');
  });

  it('prints the location on a Buy row, whose suggestion names no warehouse', async () => {
    renderView([contribution()]);
    await screen.findByText('SO428264');
    const row = rowOf('SO428264');
    expect(within(row).getByText('Buy 42')).toBeInTheDocument();
    const cell = within(row).getByTestId('board-list-location-so-1:line-80');
    expect(cell).toHaveTextContent('BRW-BB');
  });

  it('shows the code only, never the warehouse name (owner, Q2): the tooltip is the code', async () => {
    renderView(threeLines);
    await screen.findByText('SO000001');
    const cell = screen.getByTestId('board-list-location-so-2:line-2');
    expect(cell).toHaveTextContent(/^BRW-BB$/);
    expect(cell).toHaveAttribute('title', 'BRW-BB');
  });

  it('hides and shows from the Columns menu like any other column (owner, Q1)', async () => {
    renderView(threeLines);
    await screen.findByText('SO000001');
    expect(screen.getByRole('button', { name: 'Location' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Columns' }));
    await userEvent.click(await screen.findByRole('menuitemcheckbox', { name: 'Location' }));
    await userEvent.keyboard('{Escape}');
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Location' })).not.toBeInTheDocument(),
    );

    await userEvent.click(screen.getByRole('button', { name: 'Columns' }));
    await userEvent.click(await screen.findByRole('menuitemcheckbox', { name: 'Location' }));
    await userEvent.keyboard('{Escape}');
    expect(await screen.findByRole('button', { name: 'Location' })).toBeInTheDocument();
  });

  it('is a draggable column, reorderable like Product beside it (owner, Q1)', async () => {
    renderView(threeLines);
    await screen.findByText('SO000001');
    const locationCell = screen.getByTestId('board-list-location-so-1:line-1').closest('td');
    const productCell = within(rowOf('SO000001'))
      .getByText('SRTWT7445-LV')
      .closest('td');
    // The grid marks a fixed utility column (select, expand) `data-dnd-disabled`; an
    // ordinary column, the ones the planner drags, carries no such mark.
    const selectCell = within(rowOf('SO000001')).getByRole('checkbox').closest('td');
    expect(selectCell).toHaveAttribute('data-dnd-disabled');
    expect(productCell).not.toHaveAttribute('data-dnd-disabled');
    expect(locationCell).not.toHaveAttribute('data-dnd-disabled');
  });

  it('says No location for a line AutoCount gave none', async () => {
    renderView([
      contribution({ fulfilment_location: null, unplannable: true }),
    ]);
    await screen.findByText('SO428264');
    expect(screen.getByTestId('board-list-location-so-1:line-80')).toHaveTextContent(
      'No location',
    );
  });

  it('sorts by location from its header', async () => {
    renderView(threeLines);
    await screen.findByText('SO000001');
    expect(screen.getAllByText(/^SO00000[1-3]$/).map((el) => el.textContent)).toEqual([
      'SO000001',
      'SO000002',
      'SO000003',
    ]);

    fireEvent.click(screen.getByRole('button', { name: 'Location' }));

    // BRW-BB, DC1-BB, WH3-BB.
    await waitFor(() =>
      expect(screen.getAllByText(/^SO00000[1-3]$/).map((el) => el.textContent)).toEqual([
        'SO000002',
        'SO000003',
        'SO000001',
      ]),
    );
  });

  it('filters by location, several at once, from the Filters menu', async () => {
    renderView(threeLines);
    await screen.findByText('SO000001');

    await userEvent.click(screen.getByRole('button', { name: /^Filters/ }));
    await userEvent.click(await locationFilterTrigger());
    await userEvent.click(await screen.findByRole('option', { name: /^BRW-BB/ }));
    await userEvent.click(await screen.findByRole('option', { name: /^DC1-BB/ }));
    await userEvent.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByText('SO000001')).not.toBeInTheDocument());
    expect(screen.getByText('SO000002')).toBeInTheDocument();
    expect(screen.getByText('SO000003')).toBeInTheDocument();
    expect(screen.getByText('Location: BRW-BB, DC1-BB')).toBeInTheDocument();
  });

  it('offers No location as a filter option and keeps only those lines', async () => {
    renderView([
      ...threeLines,
      contribution({
        key: 'so-4:line-4',
        so_number: 'SO000004',
        line_no: 4,
        fulfilment_location: null,
        unplannable: true,
      }),
    ]);
    await screen.findByText('SO000004');

    await userEvent.click(screen.getByRole('button', { name: /^Filters/ }));
    await userEvent.click(await locationFilterTrigger());
    await userEvent.click(await screen.findByRole('option', { name: /^No location/ }));
    await userEvent.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByText('SO000002')).not.toBeInTheDocument());
    expect(screen.getByText('SO000004')).toBeInTheDocument();
  });

  it('takes the Location filter from the board when handed in, so it outlives a view switch', async () => {
    const onChange = vi.fn();
    render(
      <FulfilmentBoardListView
        contributions={threeLines}
        draft={{}}
        onDecide={vi.fn()}
        onDecideMany={vi.fn(async () => ({ saved: 0, failed: 0 }))}
        onDecideBatch={vi.fn(async () => ({ savedKeys: [], failed: [] }))}
        locationFilterState={{ value: ['DC1-BB'], onChange }}
      />,
    );
    await screen.findByText('SO000003');
    expect(screen.queryByText('SO000001')).not.toBeInTheDocument();
    expect(screen.queryByText('SO000002')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /^Filters/ }));
    await userEvent.click(await locationFilterTrigger());
    await userEvent.click(await screen.findByRole('option', { name: /^BRW-BB/ }));
    expect(onChange).toHaveBeenCalledWith(['DC1-BB', 'BRW-BB']);
  });

  it('keeps a picked location as an option after its last line leaves the board', async () => {
    render(
      <FulfilmentBoardListView
        contributions={threeLines}
        draft={{}}
        onDecide={vi.fn()}
        onDecideMany={vi.fn(async () => ({ saved: 0, failed: 0 }))}
        onDecideBatch={vi.fn(async () => ({ savedKeys: [], failed: [] }))}
        locationFilterState={{ value: ['MWH-BB'], onChange: vi.fn() }}
      />,
    );
    await userEvent.click(await screen.findByRole('button', { name: /^Filters/ }));
    await userEvent.click(await locationFilterTrigger());
    expect(await screen.findByRole('option', { name: /^MWH-BB/ })).toBeInTheDocument();
  });
});
