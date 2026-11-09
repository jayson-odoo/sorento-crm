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
