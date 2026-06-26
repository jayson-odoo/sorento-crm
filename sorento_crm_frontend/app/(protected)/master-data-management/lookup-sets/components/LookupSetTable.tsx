'use client';

import { DataGridTable } from '@/components/ui/data-grid-table';

interface LookupSetTableProps {
  /** True when there are no rows to render (drives the empty state). */
  isEmpty: boolean;
}

/**
 * Presentational grid body. The react-table instance + toolbar live in the
 * parent `LookupSetsList` so the canonical `DataGridListToolbar` can share the
 * same `table`; this renders only the grid (or the empty state) inside the
 * parent's `<DataGrid>` context.
 */
export default function LookupSetTable({ isEmpty }: LookupSetTableProps) {
  if (isEmpty) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        No lookup sets yet. Click &quot;Add lookup set&quot; to create one.
      </div>
    );
  }

  return <DataGridTable />;
}
