'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Trash2, Upload } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useProject,
  usePurchaseOrderMutations,
  usePurchaseOrders,
} from '../../../../_shared/hooks/useProjects';
import { POIntakeUploadDialog } from '../../../components/POIntakeUploadDialog';
import { POIntakeVersionsStrip } from '../../../components/POIntakeVersionsStrip';
import { POToSalesOrderStep } from '../../../components/POToSalesOrderStep';
import { PurchaseOrderDialog } from '../../../components/PurchaseOrderDialog';
import { PurchaseOrderLinesEditor } from '../../../components/PurchaseOrderLinesEditor';
import { SOURCE_LABELS, describeDrift } from '../../../components/PurchaseOrdersPanel';
import { formatMyr } from '../../../components/QuotationsPanel';

/**
 * One customer PO, on its own page.
 *
 * The POs tab used to render the list AND the selected PO's documents, readiness step and
 * ninety-odd lines beneath it. The client's words: "seeing everything in 1 page is very
 * cramped". The list answers "what POs are on this project"; this answers "what is in this
 * one".
 */
export function PurchaseOrderDetailClient({
  projectId,
  poId,
}: {
  projectId: string;
  poId: string;
}) {
  const router = useRouter();
  const project = useProject(projectId);
  const purchaseOrders = usePurchaseOrders(projectId);
  const { remove } = usePurchaseOrderMutations(projectId);

  const [uploading, setUploading] = React.useState(false);
  const [editing, setEditing] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);

  const po = (purchaseOrders.data ?? []).find((row) => row.id === poId) ?? null;

  if (purchaseOrders.isLoading || project.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!po || !project.data) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This purchase order could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          It may have been deleted.
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link href={`/project-sales/${projectId}?tab=pos`}>Back to POs</Link>
        </Button>
      </div>
    );
  }

  const canEdit = project.data.can_edit;
  const drift = describeDrift(po);

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">{project.data.project_code}</span>
            <Badge variant="secondary" appearance="light">
              {SOURCE_LABELS[po.po_source] ?? po.po_source}
            </Badge>
          </div>
          <h1 className="mt-1 text-xl font-semibold break-words">{po.po_number}</h1>
          <p className="text-sm text-muted-foreground break-words">
            {[
              formatMyr(po.line_total),
              po.issuing_party_name,
              po.po_date ? formatDateInMalaysia(po.po_date) : null,
              drift || null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>

        {canEdit && (
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" onClick={() => setUploading(true)}>
              <Upload className="size-4" aria-hidden />
              Upload a document
            </Button>
            <DetailActionsMenu ariaLabel="Purchase order actions">
              <DropdownMenuItem onSelect={() => setEditing(true)}>Edit the PO</DropdownMenuItem>
              <DropdownMenuItem
                variant="destructive"
                onSelect={() => setConfirmDelete(true)}
              >
                <Trash2 className="size-4" aria-hidden />
                Delete this PO
              </DropdownMenuItem>
            </DetailActionsMenu>
          </div>
        )}
      </header>

      {canEdit && (
        <POToSalesOrderStep
          projectId={projectId}
          purchaseOrder={po}
          readiness={{
            poConfirmed: Boolean(po.po_confirmed),
            scheduleConfirmed: Boolean(po.schedule_confirmed),
          }}
        />
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Documents</CardTitle>
        </CardHeader>
        <CardContent>
          <POIntakeVersionsStrip
            projectId={projectId}
            poId={po.id}
            canEdit={canEdit}
            onUpload={() => setUploading(true)}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Lines</CardTitle>
        </CardHeader>
        <CardContent>
          <PurchaseOrderLinesEditor project={project.data} po={po} />
        </CardContent>
      </Card>

      {uploading && (
        <POIntakeUploadDialog
          projectId={projectId}
          purchaseOrderId={po.id}
          purchaseOrderNumber={po.po_number}
          onDone={() => setUploading(false)}
        />
      )}

      {editing && (
        <PurchaseOrderDialog
          project={project.data}
          po={po}
          onDone={() => setEditing(false)}
        />
      )}

      <ConfirmDeleteDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Confirm delete"
        description={`Delete ${po.po_number} and its ${po.line_count} line${po.line_count === 1 ? '' : 's'}? This action cannot be undone. The project stays at PO Received, because it genuinely passed through it.`}
        onDelete={async () => {
          await remove.mutateAsync(po.id);
        }}
        onSuccess={() => router.push(`/project-sales/${projectId}?tab=pos`)}
        successMessage="Purchase order deleted"
      />
    </div>
  );
}
