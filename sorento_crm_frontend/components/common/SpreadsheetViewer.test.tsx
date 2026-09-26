/**
 * PLAN-excel-preview-26sep S1 (AC-12, AC-13): the in-app preview of a workbook in our own grid
 * style - sheet tabs matching the file's sheets, a "Go to sheet" picker once the tab strip is
 * too long to scan, a frozen header, virtualised rows, numbers right-aligned, and a grid that
 * scrolls sideways inside its own container.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SpreadsheetViewer, type SpreadsheetWorkbook } from './SpreadsheetViewer';

function sheet(title: string, rows: (string | number | null)[][], extra = {}) {
  return { title, columns: ['Item code', 'Description', 'BRW on hand'], rows, ...extra };
}

const TWO: SpreadsheetWorkbook = {
  sheets: [
    sheet('Low stock', [['A-1', 'Basin', 3]], { flagged: true, emptyText: 'Nothing low here' }),
    sheet('All', [
      ['A-1', 'Basin', 3],
      ['B-2', 'Tap', 90],
    ]),
  ],
};

describe('SpreadsheetViewer', () => {
  it('renders one line tab per sheet, the first open, and its rows', () => {
    render(<SpreadsheetViewer workbook={TWO} />);
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual(['Low stock', 'All']);
    expect(tabs[0]).toHaveAttribute('data-state', 'active');
    const grid = screen.getByRole('grid');
    expect(within(grid).getAllByRole('row')).toHaveLength(2); // header + 1 row
    expect(within(grid).getByText('Basin')).toBeInTheDocument();
  });

  it('switches sheet on a tab click and reports it', async () => {
    const onActiveSheetChange = vi.fn();
    render(<SpreadsheetViewer workbook={TWO} onActiveSheetChange={onActiveSheetChange} />);
    await userEvent.click(screen.getByRole('tab', { name: 'All' }));
    expect(onActiveSheetChange).toHaveBeenCalledWith('All');
    expect(within(screen.getByRole('grid')).getByText('Tap')).toBeInTheDocument();
  });

  it('opens the named sheet, and the first sheet when the name is gone (AC-13)', () => {
    const { rerender } = render(<SpreadsheetViewer workbook={TWO} activeSheet="All" />);
    expect(screen.getByRole('tab', { name: 'All' })).toHaveAttribute('data-state', 'active');
    rerender(<SpreadsheetViewer workbook={TWO} activeSheet="Gone" />);
    expect(screen.getByRole('tab', { name: 'Low stock' })).toHaveAttribute('data-state', 'active');
  });

  it('shows the sheet\'s own empty text on a sheet with no rows', () => {
    const wb: SpreadsheetWorkbook = {
      sheets: [sheet('X - Low', [], { flagged: true, emptyText: 'Nothing low here' })],
    };
    render(<SpreadsheetViewer workbook={wb} />);
    expect(screen.getByText('Nothing low here')).toBeInTheDocument();
  });

  it('offers "Go to sheet" only past 12 sheets', () => {
    const many: SpreadsheetWorkbook = {
      sheets: Array.from({ length: 13 }, (_, i) => sheet(`Sheet ${i + 1}`, [['A', 'B', 1]])),
    };
    const { rerender } = render(<SpreadsheetViewer workbook={TWO} />);
    expect(screen.queryByLabelText('Go to sheet')).not.toBeInTheDocument();
    rerender(<SpreadsheetViewer workbook={many} />);
    expect(screen.getByLabelText('Go to sheet')).toBeInTheDocument();
  });

  it('keeps the header row frozen and numbers right-aligned', () => {
    render(<SpreadsheetViewer workbook={TWO} />);
    const header = screen.getByRole('row', { name: /Item code/ });
    expect(header.className).toMatch(/sticky/);
    expect(header.className).toMatch(/top-0/);
    const number = screen.getByRole('gridcell', { name: '3' });
    expect(number.className).toMatch(/text-end/);
    expect(number.className).toMatch(/tabular-nums/);
  });

  it('scrolls inside its own container, both ways', () => {
    render(<SpreadsheetViewer workbook={TWO} />);
    const scroller = screen.getByTestId('spreadsheet-scroller');
    expect(scroller.className).toMatch(/overflow-auto/);
    expect(scroller.className).toMatch(/min-w-0/);
  });

  it('virtualises: 50,000 rows put only a window of them in the DOM', () => {
    const rows = Array.from({ length: 50_000 }, (_, i) => [`C-${i}`, `Row ${i}`, i]);
    render(<SpreadsheetViewer workbook={{ sheets: [sheet('Big', rows)] }} />);
    const rendered = within(screen.getByRole('grid')).getAllByRole('row');
    expect(rendered.length).toBeGreaterThan(5);
    expect(rendered.length).toBeLessThan(200);
    expect(screen.getByText('50,000 rows')).toBeInTheDocument();
  });
});
