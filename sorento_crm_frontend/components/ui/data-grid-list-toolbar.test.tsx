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
