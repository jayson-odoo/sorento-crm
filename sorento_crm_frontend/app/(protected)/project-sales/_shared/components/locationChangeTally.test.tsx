/**
 * SPLIT-SHEET-LOCATION owner change request (9 Nov 2026): the Confirm preview prints a line
 * AutoCount moved as the purchasing email and its Excel do: LOCATION the old location, NEW
 * LOCATION the new one right after it, filled only on a moved line (blank otherwise, like NEW
 * QTY). Both columns show at 375px too (LOCATION used to be desktop-only).
 */
import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { SplitLinesSheet, coveredSheetLines } from './LineSplitInfo';
import type { LineSplitLine, LineSplitsPayload } from '../types/lineSplit.types';

const FIXTURE = resolve(
  __dirname,
  '../../../../../../sorento_crm_backend/tests/fixtures/product_change_tally.json',
);
const base = (JSON.parse(readFileSync(FIXTURE, 'utf8')) as { split_read_line: LineSplitLine })
  .split_read_line;
const unswapped = { ...base, was_item_code: null };

function renderPreview(lines: LineSplitLine[]) {
  const payload = {
    pso_id: 'pso-loc',
    so_number: 'SO427856',
    so_date: '2026-11-01',
    lines,
  } as unknown as LineSplitsPayload;
  const sheet = coveredSheetLines(
    payload,
    lines.map((line) => ({
      lineId: line.line_id,
      key: `board:${line.line_no}`,
      lineNo: line.line_no,
      itemCode: line.item_code,
      location: line.location,
      qty: line.base_qty,
      date: line.base_date,
      savedRemark: null,
    })),
  );
  render(<SplitLinesSheet payload={payload} soNumber="SO427856" sheet={sheet} />);
  return screen.getByRole('table', { name: 'Split delivery sheet' });
}

const headings = (table: HTMLElement) =>
  within(table)
    .getAllByRole('columnheader')
    .map((cell) => cell.textContent ?? '');

describe('the Confirm preview prints LOCATION / NEW LOCATION as the email does', () => {
  it('a moved line: LOCATION the old location, NEW LOCATION the new one beside it', () => {
    const moved = { ...unswapped, line_no: 48, line_id: 'pl-48', location: 'BRW', was_location: 'BRW-IB' };
    const still = {
      ...unswapped, line_no: 64, line_id: 'pl-64', item_code: 'SRTSC09', location: 'BRW-BB',
      was_location: null,
    };
    const table = renderPreview([moved, still]);

    const heads = headings(table);
    expect(heads.indexOf('New location')).toBe(heads.indexOf('Location') + 1);
    expect(screen.getByTestId('location-48')).toHaveTextContent('BRW-IB');
    expect(screen.getByTestId('new-location-48')).toHaveTextContent('BRW');
    expect(screen.getByTestId('location-64')).toHaveTextContent('BRW-BB');
    expect(screen.getByTestId('new-location-64')).toHaveTextContent('');
  });

  it('no moved line: no New location column', () => {
    const table = renderPreview([{ ...unswapped, location: 'BRW-BB', was_location: null }]);
    expect(headings(table)).not.toContain('New location');
  });

  it('both columns show on a phone (neither is desktop-only)', () => {
    const moved = { ...unswapped, line_no: 48, line_id: 'pl-48', location: 'BRW', was_location: 'BRW-IB' };
    const table = renderPreview([moved]);
    const cells = within(table).getAllByRole('columnheader');
    const loc = cells.find((cell) => cell.textContent === 'Location') as HTMLElement;
    const newLoc = cells.find((cell) => cell.textContent === 'New location') as HTMLElement;
    expect(loc.className).not.toContain('max-md:hidden');
    expect(newLoc.className).not.toContain('max-md:hidden');
    expect(screen.getByTestId('location-48').className).not.toContain('max-md:hidden');
  });
});

describe('the moved-line sheet stays close to its width before the New location column (crew ruling (a), every value readable)', () => {
  const widthOf = (table: HTMLElement, label: string) => {
    const th = within(table)
      .getAllByRole('columnheader')
      .find((cell) => cell.textContent === label) as HTMLElement;
    return parseFloat(th.style.width);
  };

  it('with a moved line: the pair at 70px, Breakdown date 212px, both date columns 80px', () => {
    // Measured in Chromium, Inter 12px (9 Nov): BRW-WW 55.6px of text, so 70px with the cell's
    // padding and border; DD/MM/YYYY input + calendar button + ADVANCE pill = 211px; a date 63px.
    const moved = { ...unswapped, line_no: 48, line_id: 'pl-48', location: 'BRW', was_location: 'BRW-IB' };
    const table = renderPreview([moved]);
    expect(widthOf(table, 'Location')).toBe(70);
    expect(widthOf(table, 'New location')).toBe(70);
    expect(widthOf(table, 'Breakdown date')).toBe(212);
    expect(widthOf(table, 'Delivery date')).toBe(80);
    expect(widthOf(table, 'New date')).toBe(80);
  });

  it('with no moved line: the widths are as before (Location 64px, Breakdown date 236px)', () => {
    const table = renderPreview([{ ...unswapped, location: 'BRW-BB', was_location: null }]);
    expect(widthOf(table, 'Location')).toBe(64);
    expect(widthOf(table, 'Breakdown date')).toBe(236);
    expect(widthOf(table, 'Delivery date')).toBe(96);
  });

  it('a long location code truncates with the full code as its tooltip', () => {
    const moved = {
      ...unswapped, line_no: 48, line_id: 'pl-48', location: 'BRW-PROJECTX', was_location: 'BRW-IB',
    };
    renderPreview([moved]);
    const cell = screen.getByTestId('new-location-48');
    expect(cell.className).toContain('truncate');
    expect(cell).toHaveAttribute('title', 'BRW-PROJECTX');
    expect(screen.getByTestId('location-48')).toHaveAttribute('title', 'BRW-IB');
  });
});
