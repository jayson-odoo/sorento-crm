'use client';

import * as React from 'react';
import Link from 'next/link';
import {
  ClipboardList,
  Download,
  FileDiff,
  GitCompareArrows,
  Send,
  Shuffle,
  Table2,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useProjectSalesOrder,
  useSalesOrderImportFile,
  useSalesOrderMutations,
} from '../../../../_shared/hooks/useProjectSalesOrders';
import { useProject } from '../../../../_shared/hooks/useProjects';
import { useOpenDivergenceForOrder } from '../../../../_shared/hooks/useSoDivergence';
import type { ProjectSalesOrderFinding } from '../../../../_shared/types/projectSalesOrder.types';
import { SalesOrderAcknowledgeDialog } from '../../../components/SalesOrderAcknowledgeDialog';
import { SalesOrderFindingsSection } from '../../../components/SalesOrderFindingsSection';
import { SalesOrderLinesTable } from '../../../components/SalesOrderLinesTable';
import { formatMoney, sumMoney } from '../../../components/SalesOrderMoney';
import { SalesOrderPublishDialog } from '../../../components/SalesOrderPublishDialog';
import { SalesOrderRegroupDialog } from '../../../components/SalesOrderRegroupDialog';
import {
  GROUPING_ORIGIN_LABEL,
  SalesOrderStatusPill,
} from '../../../components/SalesOrderStatusPill';
import { AllocationPanel } from './AllocationPanel';

/**
 * One draft, reviewed rather than authored.
 *
 * Order on the page follows what a reviewer has to decide: what this order is, what stops it
 * publishing, what merely needs a reason, then the 99 lines. Every section renders even when
 * it has nothing in it, because "no warnings" is information and a missing card is not.
 */
export function SalesOrderDetailClient({
  projectId,
  psoId,
}: {
  projectId: string;
  psoId: string;
}) {
  const project = useProject(projectId);
  const salesOrder = useProjectSalesOrder(psoId);
  const { acknowledge, regroup, publish } = useSalesOrderMutations(projectId, psoId);
  const importFile = useSalesOrderImportFile(psoId);
  // Called above the early returns, as every hook must be. Keyed on the order's
  // `updated_at` so an ingest or a publish refetches it: this is what disables the amend
  // button, and a stale answer either blocks a clean order or lets a wrong amendment past.
  const { divergence } = useOpenDivergenceForOrder(psoId, salesOrder.data?.updated_at);

  const [acknowledging, setAcknowledging] = React.useState<ProjectSalesOrderFinding | null>(null);
  const [regrouping, setRegrouping] = React.useState(false);
  const [publishing, setPublishing] = React.useState(false);
  const [focusLineId, setFocusLineId] = React.useState<string | null>(null);

  if (salesOrder.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (salesOrder.isError || !salesOrder.data) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This sales order could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {salesOrder.error instanceof Error
            ? salesOrder.error.message
            : 'It may have been rebuilt or deleted.'}
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link href={`/project-sales/${projectId}?tab=sales-orders`}>Back to sales orders</Link>
        </Button>
      </div>
    );
  }

  const so = salesOrder.data;
  const reference = so.autocount_doc_no || so.provisional_ref;
  const canEdit = project.data?.can_edit ?? false;
  const findings = so.findings ?? [];
  const lines = so.lines ?? [];

  // Acknowledged is `acknowledged_at`, which is what the backend's own gate reads. The
  // name beside it is a display field and is absent whenever the acknowledger no longer
  // resolves, which would silently turn a cleared finding back into a blocking one.
  const blocking = findings.filter(
    (finding) => finding.severity === 'hard' && !finding.acknowledged_at,
  );
  const unacknowledgedWarnings = findings.filter(
    (finding) => finding.severity === 'warn' && !finding.acknowledged_at,
  );
  const isPublished = so.status === 'published' || so.status === 'amended';
  // The server owns the export gate. `can_export` is optional so a row cached from before
  // it shipped still offers the download it used to.
  const canExport = so.can_export ?? Boolean(so.import_file_url);

  // Summed from the line amounts as decimal strings so the figure can be read straight off
  // the printed order. `total_amount` is shown beside it and disagreement is worth seeing.
  const lineSum = sumMoney(lines.map((line) => line.amount));

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold break-words">{reference}</h1>
            <SalesOrderStatusPill status={so.status} />
            {so.is_pre_order && (
              <Badge variant="secondary" appearance="light">
                Pre-order
              </Badge>
            )}
            {so.is_sponsorship && (
              <Badge variant="secondary" appearance="light">
                Sponsorship
              </Badge>
            )}
          </div>
          <p className="mt-1 text-sm text-muted-foreground break-words">
            {[
              so.area_group || 'No area group',
              GROUPING_ORIGIN_LABEL[so.grouping_origin] ?? so.grouping_origin,
              so.po_number ? `Customer PO ${so.po_number}` : 'No customer PO recorded',
            ].join(' · ')}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href={`/project-sales/${projectId}/sales-orders/${psoId}/worksheet`}>
              <Table2 className="size-4" aria-hidden />
              Worksheet
            </Link>
          </Button>
          {/* Disabled rather than hidden while a difference is open: the reviewer has to
              learn WHY they cannot amend, and a button that vanished teaches nothing.
              The server refuses it too (AC-N5) - this only saves the round trip. */}
          <Button
            asChild={!divergence}
            variant="outline"
            size="sm"
            disabled={Boolean(divergence)}
            title={
              divergence
                ? 'Reconcile the AutoCount differences before amending this order'
                : undefined
            }
          >
            {divergence ? (
              <span>
                <GitCompareArrows className="size-4" aria-hidden />
                Review a revision
              </span>
            ) : (
              <Link href={`/project-sales/${projectId}/sales-orders/${psoId}/revisions`}>
                <GitCompareArrows className="size-4" aria-hidden />
                Review a revision
              </Link>
            )}
          </Button>
          {isPublished && (
            <Button asChild variant={divergence ? 'primary' : 'outline'} size="sm">
              <Link href={`/project-sales/${projectId}/sales-orders/${psoId}/divergence`}>
                <FileDiff className="size-4" aria-hidden />
                {divergence ? 'Reconcile AutoCount' : 'Compare with AutoCount'}
              </Link>
            </Button>
          )}
          {canEdit && !isPublished && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setRegrouping(true)}
              disabled={lines.length === 0}
            >
              <Shuffle className="size-4" aria-hidden />
              Move lines
            </Button>
          )}
          {canEdit && !isPublished && (
            <Button type="button" size="sm" onClick={() => setPublishing(true)}>
              <Send className="size-4" aria-hidden />
              Publish
            </Button>
          )}
          {isPublished && (
            <Button asChild variant="outline" size="sm">
              <Link href={`/project-sales/${projectId}/order-inquiries`}>
                <ClipboardList className="size-4" aria-hidden />
                Order inquiry
              </Link>
            </Button>
          )}
          {/* Shown while the order has a file, disabled while the server refuses it: the
              route 422s an export the gate has not cleared, and a button that vanished
              would not say that a blocking finding is what took it away. */}
          {so.import_file_url && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => importFile.mutate(so.provisional_ref)}
              disabled={!canExport || importFile.isPending}
              title={canExport ? undefined : 'Clear the blocking findings first'}
            >
              <Download className="size-4" aria-hidden />
              Import file
            </Button>
          )}
        </div>
      </div>

      {/* Above the summary, because it changes what the reviewer is allowed to do with
          everything below it. */}
      {divergence && (
        <div
          className="rounded-lg border border-amber-500/50 bg-amber-500/5 px-4 py-3 text-sm"
          role="status"
        >
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <span className="font-semibold text-amber-700 dark:text-amber-400">
                {`AutoCount disagrees on ${divergence.differing_count} row${divergence.differing_count === 1 ? '' : 's'}.`}
              </span>{' '}
              <span className="text-muted-foreground break-words">
                Our values are unchanged, and amendments are blocked until each row is
                answered.
                {divergence.age_days > 0
                  ? ` Waiting ${divergence.age_days} day${divergence.age_days === 1 ? '' : 's'}.`
                  : ''}
              </span>
            </div>
            <Button asChild size="sm" className="shrink-0">
              <Link href={`/project-sales/${projectId}/sales-orders/${psoId}/divergence`}>
                Reconcile
              </Link>
            </Button>
          </div>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">This sales order</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Billed to" value={so.customer_name || '-'} />
          <Field label="Lines" value={so.line_count.toLocaleString()} />
          <Field label="Value" value={formatMoney(so.total_amount)} />
          <Field
            label="Sum of the lines"
            value={lines.length > 0 ? formatMoney(lineSum) : 'No lines loaded'}
          />
          <Field
            label="Drafted"
            value={so.created_at ? formatDateInMalaysia(so.created_at) : 'Unknown'}
          />
          <Field
            label="Published"
            value={so.published_at ? formatDateInMalaysia(so.published_at) : 'Not published yet'}
          />
          <Field
            label="AutoCount document"
            value={so.autocount_doc_no || 'Not adopted yet'}
          />
          <Field label="Reference we raised" value={so.provisional_ref} />
        </CardContent>
      </Card>

      {blocking.length > 0 && !isPublished && (
        <div
          className="rounded-lg border border-destructive/50 bg-destructive/5 px-4 py-3 text-sm"
          role="status"
        >
          <span className="font-semibold text-destructive">
            {`Publishing is refused: ${blocking.length} finding${
              blocking.length === 1 ? '' : 's'
            } must be fixed or overridden.`}
          </span>
        </div>
      )}

      <SalesOrderFindingsSection
        findings={findings}
        canEdit={canEdit && !isPublished}
        onAcknowledge={setAcknowledging}
        onFocusLine={setFocusLineId}
      />

      <SalesOrderLinesTable
        lines={lines}
        findings={findings}
        focusLineId={focusLineId}
        onClearFocus={() => setFocusLineId(null)}
      />

      <AllocationPanel psoId={psoId} canEdit={canEdit} />

      {acknowledging && (
        <SalesOrderAcknowledgeDialog
          finding={acknowledging}
          submitting={acknowledge.isPending}
          onDone={() => setAcknowledging(null)}
          onConfirm={(reason) =>
            acknowledge.mutateAsync({ findingId: acknowledging.id, reason })
          }
        />
      )}

      {regrouping && (
        <SalesOrderRegroupDialog
          lines={lines}
          currentAreaGroup={so.area_group || 'UNGROUPED'}
          submitting={regroup.isPending}
          onDone={() => setRegrouping(false)}
          onConfirm={(groups) => regroup.mutateAsync(groups)}
        />
      )}

      {publishing && (
        <SalesOrderPublishDialog
          reference={reference}
          blocking={blocking}
          unacknowledgedWarnings={unacknowledgedWarnings}
          submitting={publish.isPending}
          downloading={importFile.isPending}
          onDone={() => setPublishing(false)}
          onPublish={() => publish.mutateAsync()}
          onDownloadImportFile={() => importFile.mutate(so.provisional_ref)}
        />
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 break-words text-sm font-medium" title={value}>
        {value}
      </p>
    </div>
  );
}
