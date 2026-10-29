/**
 * PRODUCT-CHANGE-TALLY (owner, 28 Oct 2026, SO426847 line 48): "I thought the email, popup
 * preview and the attachment supposed to tally". The Confirm preview's sheet prints a product
 * AutoCount swapped as the email and its Excel do: ITEM CODE the old code, NEW ITEM CODE the
 * new one beside it, and the same REMARK.
 *
 * Read off the SAME fixture the backend's `tests/test_product_change_tally.py` renders the
 * email and the attachment from (`split_read_line` is that line as the split read sends it),
 * against the same `expected`, so the three cannot drift apart.
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

interface TallyFixture {
  split_read_line: LineSplitLine;
  so_number: string;
  so_date: string;
  expected: { item_code: string; new_item_code: string; remark: string };
}

const fixture = JSON.parse(readFileSync(FIXTURE, 'utf8')) as TallyFixture;

function renderPreview(lines: LineSplitLine[]) {
  const payload = {
    pso_id: 'pso-tally',
    so_number: fixture.so_number,
    so_date: fixture.so_date,
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
  render(<SplitLinesSheet payload={payload} soNumber={fixture.so_number} sheet={sheet} />);
  return screen.getByRole('table', { name: 'Split delivery sheet' });
}

const headings = (table: HTMLElement) =>
  within(table)
    .getAllByRole('columnheader')
    .map((cell) => cell.textContent ?? '');

describe('the Confirm preview tallies with the Order Inquiry email and its attachment', () => {
  it('a swapped line prints ITEM CODE (old), NEW ITEM CODE (new) and the email REMARK', () => {
    const table = renderPreview([fixture.split_read_line]);
    const no = fixture.split_read_line.line_no;
    const { expected } = fixture;

    const heads = headings(table);
    expect(heads.indexOf('New item code')).toBe(heads.indexOf('Item code') + 1);
    expect(screen.getByTestId(`item-code-${no}`)).toHaveTextContent(expected.item_code);
    expect(screen.getByTestId(`new-item-code-${no}`)).toHaveTextContent(expected.new_item_code);
    const row = screen.getByTestId(`item-code-${no}`).closest('tr') as HTMLElement;
    expect(row).toHaveTextContent(expected.remark);
  });

  it('with no swap on the sheet there is no New item code column, as the email prints none', () => {
    const table = renderPreview([
      {
        ...fixture.split_read_line,
        item_code: fixture.expected.item_code,
        was_item_code: null,
        remark_generated: 'REMAIN',
      },
    ]);
    expect(headings(table)).not.toContain('New item code');
    const item = screen.getByTestId(`item-code-${fixture.split_read_line.line_no}`);
    expect(item).toHaveTextContent(fixture.expected.item_code);
    // A line the board says sends nothing prints no REMARK: the read's words stay out of it.
    expect(item.closest('tr')).not.toHaveTextContent('REMAIN');
  });
});
