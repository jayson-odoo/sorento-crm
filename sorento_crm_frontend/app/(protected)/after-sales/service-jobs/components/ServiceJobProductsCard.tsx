'use client';

import { useMemo, useState } from 'react';
import { ColumnDef } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { formatCivilDate } from '../../warranty/lib/warrantyLabels';
import { useServiceJobProducts } from '../hooks/useServiceJobProducts';
import type { ServiceJobProduct } from '../types/serviceJob.types';
import ServiceJobProductDialog from './ServiceJobProductDialog';
import { codeWithName, distinctName } from '@/lib/product-display';

function Text({ value }: { value: string | null | undefined }) {
  return (
    <span className="block truncate" title={value || undefined}>
      {value || '-'}
    </span>
  );
}

const col = (
  id: string,
  title: string,
  size: number,
  value: (l: ServiceJobProduct) => string | null | undefined,
): ColumnDef<ServiceJobProduct> => ({
  id,
  header: title,
  size,
  cell: ({ row }) => <Text value={value(row.original)} />,
  meta: { headerTitle: title, skeleton: <Skeleton className="h-4 w-20" /> },
});

export default function ServiceJobProductsCard({ jobId, canEdit }: { jobId: string; canEdit: boolean }) {
  const { data, isLoading, isError, refetch } = useServiceJobProducts(jobId);
  const [dialog, setDialog] = useState<{ open: boolean; line: ServiceJobProduct | null }>({
    open: false,
    line: null,
  });
  const [menuLine, setMenuLine] = useState<ServiceJobProduct | null>(null);
  const remove = useDeferredRowAction({
    actionKey: 'service_job_product.delete',
    entityType: 'service_job_product',
    verb: 'Removing',
    successMessage: 'Product removed.',
    invalidateKeys: [['service-job-products'], ['service-job'], ['service-jobs']],
  });

  const columns = useMemo<ColumnDef<ServiceJobProduct>[]>(
    () => [
      col('product_code', 'Product code', 150, (l) => l.product_code),
      col('product_name', 'Description', 260, (l) => distinctName(l.product_code, l.product_name)),
      col('kind', 'Kind', 160, (l) => l.kind_name),
      col('purchase_date', 'Purchase date', 130, (l) => (l.purchase_date ? formatCivilDate(l.purchase_date) : null)),
      col('defect', 'Defect', 140, (l) => l.defect_label),
    ],
    [],
  );
  const lines = data ?? [];

  const grid = (
    <PanelDataGrid<ServiceJobProduct>
      title="Products"
      toolbar={
        canEdit ? (
          <Button variant="outline" size="sm" onClick={() => setDialog({ open: true, line: null })}>
            <Plus />
            Add product
          </Button>
        ) : undefined
      }
      columns={columns}
      rows={lines}
      getRowId={(l) => l.id}
      listingKey={null}
      paginate={false}
      isLoading={isLoading}
      error={isError ? new Error('Failed to load the products') : undefined}
      onRetry={() => void refetch()}
      rowAttributes={(l) => ({ 'data-line-id': l.id })}
      emptyTitle="No products"
      emptyBody="Add the products this visit is about."
    />
  );

  return (
    <>
      {canEdit ? (
        <ContextMenu modal={false}>
          <ContextMenuTrigger asChild>
            <div
              // A right-click outside a row stops here, so the browser's own menu shows.
              onContextMenuCapture={(event) => {
                const el = (event.target as Element).closest('[data-line-id]');
                const line = lines.find((l) => l.id === el?.getAttribute('data-line-id'));
                if (!line) {
                  event.stopPropagation();
                  return;
                }
                setMenuLine(line);
              }}
            >
              {grid}
            </div>
          </ContextMenuTrigger>
          <ContextMenuContent className="w-48">
            {menuLine && (
              <>
                <ContextMenuItem onSelect={() => setDialog({ open: true, line: menuLine })}>Edit</ContextMenuItem>
                <ContextMenuItem
                  onSelect={() =>
                    remove.run({
                      id: menuLine.id,
                      subject: codeWithName(menuLine.product_code, menuLine.product_name),
                    })
                  }
                >
                  Remove
                </ContextMenuItem>
              </>
            )}
          </ContextMenuContent>
        </ContextMenu>
      ) : (
        grid
      )}
      <ServiceJobProductDialog
        open={dialog.open}
        onOpenChange={(open) => setDialog((d) => ({ ...d, open }))}
        jobId={jobId}
        line={dialog.line}
      />
    </>
  );
}
