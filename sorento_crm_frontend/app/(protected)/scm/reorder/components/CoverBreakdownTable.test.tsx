/**
 * The decision breakdown, as a table (AC-3.1).
 *
 * The hover used to be a sentence ("Use 5 from BRW-BB, 1 from PJ-SR, and buy 182"), which
 * stopped being readable at the second location and left the buyer adding the parts up to
 * check they came to the shortage. Every part is a row now, and the total is printed.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { CoverBreakdownTable } from './CoverBreakdownTable';

const rowsOf = (): string[][] =>
  screen
    .getAllByRole('row')
    .map((r) => within(r).getAllByRole('cell').map((c) => c.textContent ?? ''));

describe('CoverBreakdownTable', () => {
  it('lists one row per location, then the buy, then the total', () => {
    render(
      <CoverBreakdownTable
        sources={[
          { warehouse_code: 'BRW-BB', qty: 5 },
          { warehouse_code: 'PJ-SR', qty: 1 },
        ]}
        buyQty={182}
      />,
    );
    expect(rowsOf()).toEqual([
      ['BRW-BB', '5'],
      ['PJ-SR', '1'],
      ['Buy', '182'],
      ['Total', '188'],
    ]);
  });

  it('is a pure buy when no location gives anything', () => {
    render(<CoverBreakdownTable sources={[]} buyQty={1778} />);
    expect(rowsOf()).toEqual([
      ['Buy', '1,778'],
      ['Total', '1,778'],
    ]);
  });

  it('names the PO part so the total still adds up', () => {
    render(
      <CoverBreakdownTable
        sources={[{ warehouse_code: 'BRW-BB', qty: 15 }]}
        poQty={120}
        buyQty={5}
      />,
    );
    expect(rowsOf()).toEqual([
      ['BRW-BB', '15'],
      ['PO', '120'],
      ['Buy', '5'],
      ['Total', '140'],
    ]);
  });

  it('says Bought in the past tense once the decision is taken', () => {
    render(
      <CoverBreakdownTable
        sources={[{ warehouse_code: 'BRW-BB', qty: 5 }]}
        buyQty={10}
        buyLabel="Bought"
      />,
    );
    expect(screen.getByText('Bought')).toBeInTheDocument();
    expect(screen.queryByText('Buy')).not.toBeInTheDocument();
  });

  it('drops a zero part rather than printing a row that means nothing', () => {
    render(<CoverBreakdownTable sources={[{ warehouse_code: 'BRW-BB', qty: 5 }]} buyQty={0} />);
    expect(rowsOf()).toEqual([
      ['BRW-BB', '5'],
      ['Total', '5'],
    ]);
  });

  it('carries a title when the surface needs to name the row it belongs to', () => {
    render(<CoverBreakdownTable sources={[]} buyQty={3} title="Accept for SKU-1" />);
    expect(screen.getByText('Accept for SKU-1')).toBeInTheDocument();
  });
});
