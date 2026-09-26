/**
 * PLAN-excel-preview-26sep S1 (AC-12, AC-13): the in-app preview of a workbook in our own grid
 * style - sheet tabs matching the file's sheets, a "..." on the tab strip that searches every sheet
 * (owner hand test 26 Sep, Excel's own sheet list), a row search on named columns, a frozen header, virtualised rows, numbers right-aligned, and a grid that
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

const MANY: SpreadsheetWorkbook = {
  sheets: [
    ...Array.from({ length: 11 }, (_, i) => sheet(`Supplier ${i + 1}`, [['A', 'B', 1]])),
    sheet('Kohler Asia - Low', [['K-1', 'Toilet', 1]], { flagged: true }),
    sheet('Kohler Asia', [['K-1', 'Toilet', 1]]),
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

  it('W2: no jump-to-sheet dropdown under the tab strip, however many sheets', () => {
    render(<SpreadsheetViewer workbook={MANY} />);
    expect(screen.queryByLabelText('Go to sheet')).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('W3: "..." on the tab strip lists every sheet, filters as you type, and opens the one clicked', async () => {
    const onActiveSheetChange = vi.fn();
    const scrolled: string[] = [];
    const spy = vi
      .spyOn(Element.prototype, 'scrollIntoView')
      .mockImplementation(function (this: Element) {
        scrolled.push(this.textContent ?? '');
      });
    render(<SpreadsheetViewer workbook={MANY} onActiveSheetChange={onActiveSheetChange} />);

    const more = screen.getByRole('button', { name: 'All sheets' });
    // Built into the strip, beside the tabs, as Excel's sheet bar.
    const bar = more.closest('[data-slot="spreadsheet-sheet-bar"]');
    expect(bar).not.toBeNull();
    expect(within(bar as HTMLElement).getByRole('tablist', { name: 'Sheets' })).toBeInTheDocument();

    await userEvent.click(more);
    const search = await screen.findByPlaceholderText('Search sheets');
    expect(screen.getAllByRole('option')).toHaveLength(13);
    await userEvent.type(search, 'kohler');
    const options = screen.getAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual(['Kohler Asia - Low', 'Kohler Asia']);

    scrolled.length = 0;
    await userEvent.click(options[1]);

    expect(onActiveSheetChange).toHaveBeenCalledWith('Kohler Asia');
    expect(screen.getByRole('tab', { name: 'Kohler Asia' })).toHaveAttribute('data-state', 'active');
    expect(screen.queryByPlaceholderText('Search sheets')).not.toBeInTheDocument();
    // The strip scrolls to the tab it opened.
    expect(scrolled).toContain('Kohler Asia');
    spy.mockRestore();
  });

  it('W4: searches the open sheet by the named columns, the row count following', async () => {
    render(
      <SpreadsheetViewer
        workbook={TWO}
        activeSheet="All"
        searchColumns={['Item code', 'Description']}
        searchPlaceholder="Search product code"
      />,
    );
    const box = screen.getByRole('searchbox', { name: 'Search product code' });
    expect(screen.getByText('2 rows')).toBeInTheDocument();

    await userEvent.type(box, 'b-2');
    const grid = screen.getByRole('grid');
    expect(within(grid).getByText('Tap')).toBeInTheDocument();
    expect(within(grid).queryByText('Basin')).not.toBeInTheDocument();
    expect(screen.getByText('1 row')).toBeInTheDocument();

    await userEvent.clear(box);
    await userEvent.type(box, 'basin');
    expect(within(grid).getByText('Basin')).toBeInTheDocument();
    expect(screen.getByText('1 row')).toBeInTheDocument();

    // Only the named columns: "90" is BRW on hand, not a code or a description.
    await userEvent.clear(box);
    await userEvent.type(box, '90');
    expect(screen.getByText('0 rows')).toBeInTheDocument();
    expect(screen.getByText('No matching rows')).toBeInTheDocument();
  });

  it('W4: no search box when no columns are named', () => {
    render(<SpreadsheetViewer workbook={TWO} />);
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument();
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
