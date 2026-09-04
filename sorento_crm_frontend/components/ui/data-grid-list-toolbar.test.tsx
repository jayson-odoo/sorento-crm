/**
 * Tests for the canonical DataGridListToolbar (PLAN-unified-list-toolbar).
 * Covers the rules baked into the toolbar so pages can't diverge:
 * - Export is selection-gated (D4 / AC-D1)
 * - Filters renders only when wired (D3 / AC-B1)
 * - Secondary actions: 1 inline, >=2 overflow (D7 / AC-I1/I2)
 * - Bulk strip appears with count on selection (H / AC-H1)
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import {
  useReactTable,
  getCoreRowModel,
  type ColumnDef,
} from '@tanstack/react-table';
import { DataGridListToolbar } from './data-grid-list-toolbar';
import { buildSelectColumn } from './data-grid-select-column';
import { TooltipProvider } from './tooltip';

type Row = { id: string; name: string };
const DATA: Row[] = [
  { id: '1', name: 'Alpha' },
  { id: '2', name: 'Beta' },
];

const COLUMNS: ColumnDef<Row>[] = [
  buildSelectColumn<Row>(),
  { accessorKey: 'name', header: 'Name', meta: { headerTitle: 'Name' } },
];

function Harness(props: {
  toolbarProps?: Partial<React.ComponentProps<typeof DataGridListToolbar<Row>>>;
  initialSelection?: Record<string, boolean>;
}) {
  const [rowSelection, setRowSelection] = React.useState(props.initialSelection ?? {});
  const table = useReactTable({
    data: DATA,
    columns: COLUMNS,
    getRowId: (r) => r.id,
    state: { rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
  });
  // data-grid-list-toolbar.tsx no longer mounts its own TooltipProvider
  // (M2-07, one root TooltipProvider in ClientProviders.tsx) - Tooltip
  // throws without an ancestor provider, so the harness supplies one.
  return (
    <TooltipProvider>
      <DataGridListToolbar table={table} {...props.toolbarProps} />
    </TooltipProvider>
  );
}

describe('DataGridListToolbar', () => {
  it('disables Export until a row is selected (D4)', () => {
    render(<Harness toolbarProps={{ exportConfig: { filename: 'x.xlsx' } }} />);
    const exportBtn = screen.getByRole('button', { name: /export/i });
    expect(exportBtn).toBeDisabled();
  });

  it('enables Export when rows are selected, and shows the bulk strip with count (D4/H)', () => {
    render(
      <Harness
        initialSelection={{ '1': true }}
        toolbarProps={{ exportConfig: { filename: 'x.xlsx' }, bulkActions: [{ key: 'del', label: 'Delete', destructive: true, onClick: () => {} }] }}
      />,
    );
    expect(screen.getByText(/1 selected/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^export$/i })).toBeEnabled();
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /clear/i })).toBeInTheDocument();
  });

  it('hides its own Export button when the page owns it, and keeps the filename', () => {
    // A page whose right cluster owns Export used to say `exportConfig={false}`, which also
    // threw away the filename - so the file downloaded as `export.xlsx`. `showExport` is the
    // same shape as `showColumns`: hide the control, keep the configuration.
    const openers: Array<() => void> = [];
    render(
      <Harness
        initialSelection={{ '1': true }}
        toolbarProps={{
          showExport: false,
          exportConfig: { filename: 'proforma-invoices-20260828.xlsx' },
          primaryAction: ({ openExport }) => {
            openers.push(openExport);
            return <button type="button" onClick={openExport}>Export from the gear</button>;
          },
        }}
      />,
    );

    expect(screen.queryByRole('button', { name: /^export$/i })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Export from the gear' }));
    expect(screen.getByRole('button', { name: /download excel/i })).toBeInTheDocument();
  });

  it('hides the search while rows are selected, unless the page opts out (D2/H)', () => {
    render(
      <Harness
        initialSelection={{ '1': true }}
        toolbarProps={{ exportConfig: false, searchSlot: <input placeholder="Search rows" /> }}
      />,
    );
    expect(screen.queryByPlaceholderText('Search rows')).toBeNull();
  });

  it('keeps the search beside the bulk strip when keepSearchWhileSelected is set', () => {
    render(
      <Harness
        initialSelection={{ '1': true }}
        toolbarProps={{
          exportConfig: false,
          searchSlot: <input placeholder="Search rows" />,
          keepSearchWhileSelected: true,
        }}
      />,
    );
    // Both, at once: the search is how the next order to tick is found, and the strip is
    // what says how many are ticked already.
    expect(screen.getByPlaceholderText('Search rows')).toBeInTheDocument();
    expect(screen.getByText(/1 selected/i)).toBeInTheDocument();
    // The search comes FIRST, where it sits when nothing is selected, so it does not move
    // under the cursor the moment a row is ticked.
    const search = screen.getByPlaceholderText('Search rows');
    const badge = screen.getByText(/1 selected/i);
    expect(search.compareDocumentPosition(badge) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  /**
   * A tick made on a page (or a search) that is no longer loaded: the key is in
   * `rowSelection`, but the row is not in the table's row model.
   */
  it('counts only the loaded rows in the bulk strip by default', () => {
    render(<Harness initialSelection={{ '1': true, 'off-page': true }} toolbarProps={{ exportConfig: false }} />);
    expect(screen.getByText(/1 selected/i)).toBeInTheDocument();
  });

  it('counts the whole accumulated selection when keepSearchWhileSelected is set', () => {
    render(
      <Harness
        initialSelection={{ '1': true, 'off-page': true }}
        toolbarProps={{ exportConfig: false, keepSearchWhileSelected: true }}
      />,
    );
    // The page that opted into ticking across searches is counting the SET, so the strip has
    // to agree with the count its own action button shows.
    expect(screen.getByText(/2 selected/i)).toBeInTheDocument();
  });

  it('does NOT render a Filters button when no filters are wired (D3)', () => {
    render(<Harness toolbarProps={{ exportConfig: false }} />);
    expect(screen.queryByRole('button', { name: /filters/i })).toBeNull();
  });

  it('renders a Filters button when custom filters are provided (D3)', () => {
    render(
      <Harness
        toolbarProps={{ exportConfig: false, filters: { kind: 'custom', active: false, content: <div>filter body</div> } }}
      />,
    );
    expect(screen.getByRole('button', { name: /filters/i })).toBeInTheDocument();
  });

  it('renders a single secondary action inline (D7)', () => {
    render(
      <Harness
        toolbarProps={{ exportConfig: false, secondaryActions: [{ key: 'imp', label: 'Import', onClick: () => {} }] }}
      />,
    );
    expect(screen.getByRole('button', { name: /import/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^actions$/i })).toBeNull();
  });

  it('collapses >=2 secondary actions into an overflow menu (D7)', () => {
    render(
      <Harness
        toolbarProps={{
          exportConfig: false,
          secondaryActions: [
            { key: 'imp', label: 'Import', onClick: () => {} },
            { key: 'tpl', label: 'Template', onClick: () => {} },
          ],
        }}
      />,
    );
    // Inline buttons collapsed; an "Actions" overflow trigger appears instead.
    expect(screen.getByRole('button', { name: /actions/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^import$/i })).toBeNull();
  });
  it('states an active custom filter as a chip above the grid (AC-C1)', () => {
    render(
      <Harness
        toolbarProps={{
          exportConfig: false,
          filters: {
            kind: 'custom',
            active: true,
            activeCount: 1,
            activeSummary: { label: 'Pending purchasing', onClear: () => {} },
            content: <div>filter body</div>,
          },
        }}
      />,
    );
    expect(screen.getByText('Pending purchasing')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /clear filter: pending purchasing/i }),
    ).toBeInTheDocument();
  });

  it('renders no chip when the filter is not active (AC-C3)', () => {
    render(
      <Harness
        toolbarProps={{
          exportConfig: false,
          filters: {
            kind: 'custom',
            active: false,
            activeSummary: { label: 'Pending purchasing', onClear: () => {} },
            content: <div>filter body</div>,
          },
        }}
      />,
    );
    expect(screen.queryByText('Pending purchasing')).toBeNull();
  });

  it('renders no chip for a listing that supplies no summary (AC-C3)', () => {
    render(
      <Harness
        toolbarProps={{
          exportConfig: false,
          filters: { kind: 'custom', active: true, activeCount: 2, content: <div>filter body</div> },
        }}
      />,
    );
    expect(screen.queryByRole('button', { name: /clear filter/i })).toBeNull();
    // The count badge on the Filters button is unchanged.
    expect(screen.getByRole('button', { name: /filters/i })).toHaveTextContent('2');
  });

  it('fires the chip clear handler (AC-C2)', () => {
    const onClear = vi.fn();
    render(
      <Harness
        toolbarProps={{
          exportConfig: false,
          filters: {
            kind: 'custom',
            active: true,
            activeCount: 1,
            activeSummary: { label: 'Responded', onClear },
            content: <div>filter body</div>,
          },
        }}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /clear filter: responded/i }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });
  it('S1-11: a control the list puts in the search slot wraps too', () => {
    render(
      <Harness
        toolbarProps={{
          exportConfig: false,
          searchSlot: (
            <div className="flex items-center gap-2">
              <input aria-label="Search" />
              <button type="button">Quick filters</button>
            </div>
          ),
        }}
      />,
    );

    const slot = document.querySelector('[data-slot="data-grid-list-toolbar-search"]') as HTMLElement;
    expect(slot).not.toBeNull();

    // Promotions and SPO Allocations both hand the toolbar a NESTED flex row -
    // search box plus "Quick filters" / "Group by" - with no wrap of its own, so
    // at 375 it ran past the viewport edge and took the page sideways with it.
    // The list should not have to remember; the slot makes its own children wrap.
    expect(slot).toHaveClass('flex-wrap');
    expect(slot.className).toContain('[&>*]:flex-wrap');
    expect(slot.className).toContain('[&>*]:min-w-0');
  });

  it('S1-11: its controls wrap instead of running past the viewport edge', () => {
    render(<Harness toolbarProps={{ exportConfig: { filename: 'x.xlsx' } }} />);

    const toolbar = document.querySelector('[data-slot="data-grid-list-toolbar"]');
    expect(toolbar).not.toBeNull();

    // The row that holds the two clusters is the one that has to wrap; at 375 it
    // is already a column, so the rule only bites at a narrow desktop width.
    const clusterRow = toolbar!.firstElementChild;
    expect(clusterRow).toHaveClass('flex-wrap');
    expect(clusterRow).toHaveClass('sm:flex-row');
  });
});
