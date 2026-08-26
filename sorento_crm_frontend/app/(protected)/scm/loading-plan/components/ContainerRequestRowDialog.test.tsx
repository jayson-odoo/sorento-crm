import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';

import { ContainerRequestRowDialog } from './ContainerRequestRowDialog';
import type { ContainerRequestRow } from '../../services/fulfilmentService';

function row(over: Partial<ContainerRequestRow> = {}): ContainerRequestRow {
  return {
    product_id: 'p1',
    item_code: 'SRTWB241',
    product_name: 'Wall hung basin 600mm',
    open_so_need: 3999,
    suggested_qty: 2426,
    on_hand: 1573,
    on_hand_group: 640,
    incoming_spo: 0,
    incoming_spo_group: 0,
    incoming_pl: 600,
    incoming_pl_shipments: [
      { shipment_id: 's1', shipment_number: null, estimated_arrival_date: null, qty: 400 },
      {
        shipment_id: 's2',
        shipment_number: 'FSCU8103365',
        estimated_arrival_date: '2026-07-27',
        qty: 200,
      },
    ],
    outstanding_po: 297,
    outstanding_po_lines: [
      { po_number: '202607-S0105', expected_date: '2026-09-30', qty: 297 },
    ],
    sites: [
      { warehouse_code: 'BRW', on_hand: 1573, incoming_spo: 0 },
      { warehouse_code: 'MWH', on_hand: 0, incoming_spo: 0 },
      { warehouse_code: 'WH3', on_hand: 0, incoming_spo: 0 },
    ],
    group_locations: {
      count: 12,
      on_hand: 640,
      incoming_spo: 0,
      warehouse_codes: ['BRW-BB', 'DC1-BB'],
    },
    project_qty: 2229,
    retail_qty: 1770,
    unclassified_qty: 0,
    earliest_required_date: '2024-11-20',
    so_count: 37,
    holding_source: 'stock_list' as const,
    holding_qty: 522,
    holding_as_of: null,
    qty_packed: 522,
    qty_unfinished: 1411,
    cbm_per_unit: 0.11,
    row_as_of: '2026-08-21',
    rank: 1,
    rank_score: 0.94,
    rank_factors: [],
    has_demand: true,
    ...over,
  };
}

function renderDialog(over: Partial<ContainerRequestRow> = {}, askQty = 2426) {
  return render(
    <ContainerRequestRowDialog
      row={row(over)}
      askQty={askQty}
      soLines={[
        {
          product_id: 'p1',
          item_code: 'SRTWB241',
          so_number: 'SO381895',
          customer_label: 'L4 TUJU RESIDENCE',
          demand_class: 'project',
          order_date: '2026-05-01',
          required_date: '2026-08-19',
          qty: 120,
        },
      ]}
      history={undefined}
      historyLoading={false}
      onClose={vi.fn()}
    />,
  );
}

describe('ContainerRequestRowDialog', () => {
  it('opens on what is needed and what is being asked for (AC-A2.3)', () => {
    renderDialog();

    const needed = screen.getByTestId('row-quantity-needed');
    expect(needed).toHaveTextContent('3,999');
    expect(needed).toHaveTextContent('Project 2,229');
    expect(needed).toHaveTextContent('Retail 1,770');
    expect(needed).toHaveTextContent('37 open sales orders');

    const suggestion = screen.getByTestId('row-suggestion');
    expect(suggestion).toHaveTextContent('2,426');
    // The arithmetic, spelled out (AC-B5).
    expect(suggestion).toHaveTextContent('need 3,999 - pool stock 1,573 - SPO 0 = 2,426');
    expect(suggestion).toHaveTextContent(
      'Incoming PL 600 and outstanding PO 297 are not deducted',
    );
    expect(suggestion).toHaveTextContent('They hold 522 packed');
  });

  it('shows the ask she edited, not the suggestion she overrode', () => {
    renderDialog({}, 900);

    expect(screen.getByTestId('row-suggestion')).toHaveTextContent('900');
  });

  it('lists every site pool, zero rows included, and the group locations muted (AC-B1/B3)', () => {
    const table = renderDialog() && screen.getByTestId('row-locations');
    const rows = within(table).getAllByRole('row');

    // header + 3 site pools + 1 group line
    expect(rows).toHaveLength(5);
    expect(within(table).getByText('BRW')).toBeInTheDocument();
    expect(within(table).getByText('MWH')).toBeInTheDocument();
    expect(within(table).getByText('WH3')).toBeInTheDocument();
    // The group line names a couple of codes and how many there are, and its Counted cell is
    // a dash: this stock is real and deliberately not part of the ask.
    expect(within(table).getByText('BRW-BB, DC1-BB, ... (12)')).toBeInTheDocument();
    expect(within(table).getByText('Group locations')).toBeInTheDocument();
    expect(within(table).getByText('640')).toBeInTheDocument();
  });

  it('names the packing lists and open POs behind the reference figures (AC-B4)', () => {
    renderDialog();

    const incoming = screen.getByTestId('row-incoming');
    expect(incoming).toHaveTextContent('PL draft, no ETA');
    expect(incoming).toHaveTextContent('PL FSCU8103365, ETA 27/07/2026');
    expect(incoming).toHaveTextContent('PO 202607-S0105, due 30/09/2026');
  });

  it('says so when nothing is on its way, rather than showing an empty list', () => {
    renderDialog({ incoming_pl_shipments: [], outstanding_po_lines: [] });

    expect(
      screen.getByText('Nothing on a packing list or an open PO for this product.'),
    ).toBeInTheDocument();
  });

  it('lists the sales-order lines behind the row', () => {
    renderDialog();

    const lines = screen.getByTestId('row-so-lines');
    expect(within(lines).getByText('SO381895')).toBeInTheDocument();
    expect(within(lines).getByText('L4 TUJU RESIDENCE')).toBeInTheDocument();
    expect(within(lines).getByText('120')).toBeInTheDocument();
  });
});
