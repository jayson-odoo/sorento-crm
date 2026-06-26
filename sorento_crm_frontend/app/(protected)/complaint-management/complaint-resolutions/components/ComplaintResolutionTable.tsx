'use client';

import { DataGridTable } from '@/components/ui/data-grid-table';

interface Props {
  /** True when the (filtered) row set is empty. */
  isEmpty: boolean;
}

/**
 * Presentational grid body. The react-table instance + canonical toolbar live
 * in the parent `ComplaintResolutionsList`; this renders only the grid (or the
 * empty state) inside the parent's `<DataGrid>` context.
 */
export default function ComplaintResolutionTable({ isEmpty }: Props) {
  if (isEmpty) {
    return <div className="text-sm text-muted-foreground py-4">No resolutions found</div>;
  }
  return <DataGridTable />;
}
