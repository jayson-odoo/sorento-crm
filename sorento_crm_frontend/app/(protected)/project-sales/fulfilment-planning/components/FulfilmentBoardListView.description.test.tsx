/**
 * SO-LINE-DESC AC-5: the List view shows the AutoCount line description in a "Description"
 * column right after Product, taken from the core SO line the row belongs to; no description
 * is an empty cell.
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


const PUSH = 'SORENTO ACCESSORIES SRTWC8320-S150-UF PUSH BUTTON ONLY';

describe('SO-LINE-DESC: the List view carries the SO line description', () => {
  it('has a Description column right after Product', async () => {
    renderView([contribution({ description: PUSH } as Partial<BoardContribution>)]);
    await screen.findByText('SO428264');
    const headers = screen
      .getAllByRole('columnheader')
      .map((header) => header.textContent?.trim() ?? '');
    const product = headers.indexOf('Product');
    expect(product).toBeGreaterThan(-1);
    expect(headers[product + 1]).toBe('Description');
  });

  it('prints the row\'s own description, full text on hover', async () => {
    renderView([
      contribution({ description: PUSH } as Partial<BoardContribution>),
      contribution({
        key: 'so-2:line-2',
        so_number: 'SO000002',
        description: 'CABANA ACCESSORIES - TAP HEAD ONLY FOR MODEL KT886SS-NL',
      } as Partial<BoardContribution>),
    ]);
    await screen.findByText('SO428264');
    const cell = within(rowOf('SO428264')).getByText(PUSH);
    expect(cell.closest('[title]')).toHaveAttribute('title', PUSH);
    expect(
      within(rowOf('SO000002')).getByText(
        'CABANA ACCESSORIES - TAP HEAD ONLY FOR MODEL KT886SS-NL',
      ),
    ).toBeInTheDocument();
  });

  it('leaves the cell empty for a row with no description or no core line', async () => {
    renderView([
      contribution({ description: null } as Partial<BoardContribution>),
    ]);
    await screen.findByText('SO428264');
    const headers = screen
      .getAllByRole('columnheader')
      .map((header) => header.textContent?.trim() ?? '');
    const index = headers.indexOf('Description');
    expect(index).toBeGreaterThan(-1);
    const cells = within(rowOf('SO428264')).getAllByRole('cell');
    expect(cells[index].textContent?.trim()).toBe('');
  });
});
