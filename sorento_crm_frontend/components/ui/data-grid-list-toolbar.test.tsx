/**
 * Tests for the canonical DataGridListToolbar (PLAN-unified-list-toolbar).
 * Covers the rules baked into the toolbar so pages can't diverge:
 *  - Export is selection-gated (D4 / AC-D1)
 *  - Filters renders only when wired (D3 / AC-B1)
 *  - Secondary actions: 1 inline, >=2 overflow (D7 / AC-I1/I2)
 *  - Bulk strip appears with count on selection (H / AC-H1)
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
  return <DataGridListToolbar table={table} {...props.toolbarProps} />;
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
});
