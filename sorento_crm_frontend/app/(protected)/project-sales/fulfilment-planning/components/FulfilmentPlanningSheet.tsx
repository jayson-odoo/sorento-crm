'use client';

import * as React from 'react';
import Link from 'next/link';
import { ColumnDef } from '@tanstack/react-table';
import { AlertTriangle, CheckCircle2, FileDiff, RefreshCw } from 'lucide-react';
import {
  Alert,
  AlertContent,
  AlertDescription,
  AlertIcon,
  AlertTitle,
} from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useReconciliation,
  useReconciliationMutations,
} from '../../_shared/hooks/useFulfilmentPlanning';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { ReviewStatePill } from '../../_shared/components/ReviewStatePill';
import type {
  FulfilmentPlanningRow,
  ReconciliationException,
  ReconciliationLine,
  ReconciliationLineLink,
} from '../../_shared/types/fulfilmentPlanning.types';
import { SupplyCompositionSection } from './SupplyCompositionSection';

/**
 * One line's core-SO link. The four outcomes of the section 2 mapping rule and nothing
 * else: a line is never confirmed, partially confirmed or purchasing-ready here (AC-A03).
 *
 * Ambiguous carries its candidate count because the count is the instruction: two
 * candidates is a document to read, and a line with none is a different job entirely.
 */
const LINK_PALETTE: Record<ReconciliationLineLink, string> = {
  linked: 'active',
  missing: 'rejected',
  ambiguous: 'pending',
  duplicate: 'rejected',
};

function LineLinkPill({ line }: { line: ReconciliationLine }) {
  const label =
    line.link === 'linked'
      ? 'Linked'
      : line.link === 'missing'
        ? 'Missing'
        : line.link === 'duplicate'
          ? 'Duplicate'
          : `Ambiguous (${line.candidate_count} candidate${
              line.candidate_count === 1 ? '' : 's'
            })`;
  return (
    <span
      className={`${STATUS_PILL_BASE} normal-case ${statusPillClass(LINK_PALETTE[line.link])}`}
      title={line.reason || label}
    >
      {label}
    </span>
  );
}

/** One fact in the header strip. Always rendered, so an absent value states its absence. */
function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="truncate text-2xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="truncate text-sm">{children}</div>
    </div>
  );
}

function Absent({ children }: { children: React.ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>;
}

/** The exception list. Named by line number and item code, never by an id. */
function ExceptionRow({ exception }: { exception: ReconciliationException }) {
  const subject =
    exception.line_no != null
      ? `Line ${exception.line_no}${exception.item_code ? `, ${exception.item_code}` : ''}`
      : exception.item_code || 'This sales order';
  return (
    <li className="border-b border-border px-3 py-2 last:border-b-0">
      <div className="truncate text-sm font-medium" title={subject}>
        {subject}
      </div>
      <p className="mt-0.5 text-sm text-muted-foreground break-words">{exception.message}</p>
    </li>
  );
}

/**
 * The reconciliation of one Project SO, as a right slide-over off the planning row
 * (journey step 2).
 *
 * Every section renders whatever the answer is (AC-G02): a sales order with no lines, no
 * core order or no exceptions each states that in place rather than dropping the section,
 * because a card that disappears reads as a screen that has not finished loading.
 *
 * The two ways out of an exception are both somewhere else - upload the AutoCount document
 * on this order's own AutoCount screen, or answer a difference there - so the sheet offers
 * the way to that screen and the Re-run that reads the result. It never edits a link
 * itself: the mapping is deterministic, and a hand-picked pairing would be a fact no rule
 * can reproduce on the next run.
 */
export function FulfilmentPlanningSheet({
  row,
  open,
  onOpenChange,
}: {
  row: FulfilmentPlanningRow | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const reconciliation = useReconciliation(row?.id, open);
  const { rerun } = useReconciliationMutations();

  const summary = reconciliation.data;
  // The summary is the fresher of the two: a re-run can adopt a document number or resolve
  // a customer, and the row behind the sheet is whatever the list last fetched. The row is
  // the fallback so the strip is populated before the read lands.
  const docNo = summary?.autocount_doc_no ?? row?.autocount_doc_no;
  const projectName = summary?.project_name ?? row?.project_name;
  const projectCode = summary?.project_code ?? row?.project_code;
  const customerName = summary?.customer_name ?? row?.customer_name;
  const poNumber = summary?.po_number ?? row?.po_number;
  const areaGroup = summary?.area_group ?? row?.area_group;
  const lines = React.useMemo(() => summary?.lines ?? [], [summary]);
  const exceptions = React.useMemo(() => summary?.exceptions ?? [], [summary]);

  const columns = React.useMemo<ColumnDef<ReconciliationLine>[]>(
    () => [
      {
        id: 'line_no',
        header: 'No',
        cell: ({ row: line }) => (
          <span className="block truncate tabular-nums">{line.original.line_no}</span>
        ),
        size: 50,
        minSize: 44,
        meta: { headerTitle: 'No' },
      },
      {
        id: 'product_code',
        header: 'Item',
        cell: ({ row: line }) =>
          line.original.product_code ? (
            <span className="block truncate font-medium" title={line.original.product_code}>
              {line.original.product_code}
            </span>
          ) : (
            <Absent>Unresolved</Absent>
          ),
        size: 115,
        minSize: 95,
        meta: { headerTitle: 'Item' },
      },
      {
        id: 'description',
        header: 'Description',
        cell: ({ row: line }) =>
          line.original.description ? (
            <span className="block truncate" title={line.original.description}>
              {line.original.description}
            </span>
          ) : (
            <Absent>No description</Absent>
          ),
        size: 140,
        minSize: 110,
        meta: { headerTitle: 'Description' },
      },
      {
        id: 'qty',
        header: 'Qty',
        cell: ({ row: line }) => {
          const text = `${line.original.qty}${line.original.uom ? ` ${line.original.uom}` : ''}`;
          return (
            <span className="block truncate tabular-nums" title={text}>
              {text}
            </span>
          );
        },
        size: 85,
        minSize: 75,
        meta: { headerTitle: 'Qty' },
      },
      {
        id: 'delivery_date',
        header: 'Required',
        cell: ({ row: line }) =>
          line.original.delivery_date ? (
            <span className="block truncate tabular-nums">
              {formatDateInMalaysia(line.original.delivery_date)}
            </span>
          ) : (
            <Absent>No date</Absent>
          ),
        size: 115,
        minSize: 105,
        meta: { headerTitle: 'Required' },
      },
      {
        id: 'stock_location',
        header: 'Location',
        cell: ({ row: line }) =>
          line.original.stock_location ? (
            <span className="block truncate" title={line.original.stock_location}>
              {line.original.stock_location}
            </span>
          ) : (
            <Absent>Not set</Absent>
          ),
        size: 85,
        minSize: 75,
        meta: { headerTitle: 'Location' },
      },
      {
        id: 'link',
        header: 'Core line',
        cell: ({ row: line }) => <LineLinkPill line={line.original} />,
        size: 195,
        minSize: 150,
        meta: { headerTitle: 'Core line' },
      },
    ],
    [],
  );

  if (!row) return null;

  const reference = docNo || summary?.provisional_ref || row.provisional_ref;
  const headerOutcome = summary?.header.outcome;
  const reviewState = summary?.review_state ?? row.review_state;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full gap-0 overflow-y-auto p-0 sm:max-w-4xl"
        aria-describedby={undefined}
      >
        <SheetHeader className="border-b p-4 pe-12 sm:p-6 sm:pe-12">
          <SheetTitle className="min-w-0 break-words">{reference}</SheetTitle>
          <SheetDescription className="min-w-0 break-words">
            AutoCount reconciliation
          </SheetDescription>
        </SheetHeader>

        <SheetBody className="space-y-5 p-4 sm:p-6">
          {/* Header strip - what this sales order is, before what is wrong with it. */}
          <section aria-label="Sales order">
            <div className="mb-3">
              <ReviewStatePill
                state={summary?.review_state ?? row.review_state}
                exceptionCount={summary ? exceptions.length : row.exception_count}
              />
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Meta label="Project SO">
                <span className="tabular-nums">
                  {summary?.provisional_ref ?? row.provisional_ref}
                </span>
              </Meta>
              <Meta label="AutoCount doc">
                {docNo ? (
                  <span className="tabular-nums">{docNo}</span>
                ) : (
                  <Absent>Not uploaded</Absent>
                )}
              </Meta>
              <Meta label="Project">
                {projectName ? (
                  <span title={projectCode ? `${projectName} (${projectCode})` : projectName}>
                    {projectName}
                  </span>
                ) : (
                  <Absent>-</Absent>
                )}
              </Meta>
              <Meta label="Customer">
                {customerName ? (
                  <span title={customerName}>{customerName}</span>
                ) : (
                  <Absent>Not recorded</Absent>
                )}
              </Meta>
              <Meta label="Customer PO">
                {poNumber ? <span>{poNumber}</span> : <Absent>None</Absent>}
              </Meta>
              <Meta label="Area group">
                {areaGroup ? <span>{areaGroup}</span> : <Absent>No area group</Absent>}
              </Meta>
            </div>
          </section>

          {reconciliation.isError ? (
            <Alert variant="destructive" appearance="light">
              <AlertIcon>
                <AlertTriangle />
              </AlertIcon>
              <AlertContent>
                <AlertTitle>The reconciliation could not be loaded</AlertTitle>
                <AlertDescription>
                  {reconciliation.error instanceof Error
                    ? reconciliation.error.message
                    : 'Try again in a moment.'}
                  <div className="mt-3">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => reconciliation.refetch()}
                    >
                      Try again
                    </Button>
                  </div>
                </AlertDescription>
              </AlertContent>
            </Alert>
          ) : reconciliation.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-28 w-full" />
              <Skeleton className="h-48 w-full" />
            </div>
          ) : (
            <>
              {/* Reconciliation card - the header link, the count, and what is in the way. */}
              <section aria-label="Reconciliation" className="space-y-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Reconciliation
                </div>

                <div className="rounded-lg border border-border">
                  <div className="flex flex-col gap-1 border-b border-border px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="text-2xs uppercase tracking-wide text-muted-foreground">
                        Core sales order
                      </div>
                      <div className="truncate text-sm font-medium">
                        {summary?.header.core_so_number ? (
                          <span className="tabular-nums">{summary.header.core_so_number}</span>
                        ) : (
                          <Absent>Not linked</Absent>
                        )}
                      </div>
                    </div>
                    <p className="min-w-0 text-sm text-muted-foreground break-words sm:text-end">
                      {summary?.header.reason || 'No reason was given.'}
                    </p>
                  </div>
                  <div className="px-3 py-2.5">
                    <div className="text-2xs uppercase tracking-wide text-muted-foreground">
                      Lines linked
                    </div>
                    <div className="text-sm font-medium tabular-nums">
                      {summary?.lines_linked ?? 0} of {summary?.lines_total ?? 0}
                    </div>
                  </div>
                </div>

                {/* Exceptions. Rendered whether or not there are any: "every line is
                    linked" is the answer CS came for, and a missing list is not. */}
                <div className="rounded-lg border border-border">
                  <div className="border-b border-border px-3 py-2 text-2xs uppercase tracking-wide text-muted-foreground">
                    Exceptions
                  </div>
                  {exceptions.length === 0 ? (
                    <div className="flex items-center gap-2 px-3 py-4 text-sm text-muted-foreground">
                      <CheckCircle2 className="size-4 shrink-0" aria-hidden />
                      Every line is linked, and nothing on the AutoCount document is spare.
                    </div>
                  ) : (
                    <ul className="divide-y-0">
                      {exceptions.map((exception, index) => (
                        <ExceptionRow
                          key={`${exception.kind}-${exception.line_no ?? ''}-${exception.item_code ?? ''}-${index}`}
                          exception={exception}
                        />
                      ))}
                    </ul>
                  )}
                </div>

                {headerOutcome === 'no_document' && (
                  <Button asChild variant="outline" size="sm">
                    <Link
                      href={`/project-sales/${row.project_id}/sales-orders/${row.id}/divergence`}
                    >
                      <FileDiff className="size-4" aria-hidden />
                      Upload the AutoCount document
                    </Link>
                  </Button>
                )}
              </section>

              {/* Lines - one row per Project SO line, with the link the mapping produced. */}
              <section aria-label="Lines">
                <PanelDataGrid<ReconciliationLine>
                  title="Lines"
                  columns={columns}
                  rows={lines}
                  getRowId={(line) => line.id}
                  listingKey="projects.projects.view::project-so-reconciliation-lines"
                  emptyTitle="This sales order has no lines"
                  emptyBody="Nothing can be reconciled until it carries at least one line."
                  searchPlaceholder="Search item or description"
                  searchOf={(line) =>
                    [line.product_code, line.description].filter(Boolean).join(' ')
                  }
                />
              </section>

              {/* Supply composition - what meets each line, and the one press that
                  commits all of them. Rendered whatever the state is: an order still
                  mapping its lines says so here rather than dropping the section. */}
              {reviewState === 'needs_cs_review' || reviewState === 'confirmed' ? (
                <SupplyCompositionSection psoId={row.id} reference={reference} open={open} />
              ) : (
                <section aria-label="Supply composition" className="space-y-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Supply composition
                  </div>
                  <div className="rounded-lg border border-border px-3 py-8 text-center">
                    <h3 className="text-sm font-semibold">
                      Nothing can be composed for this sales order yet
                    </h3>
                    <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                      Every line needs its core sales order line first.
                    </p>
                  </div>
                </section>
              )}
            </>
          )}
        </SheetBody>

        <SheetFooter className="gap-2 border-t p-4 sm:p-6">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button
            type="button"
            onClick={() => rerun.mutate(row.id)}
            disabled={rerun.isPending || reconciliation.isLoading}
          >
            <RefreshCw className="size-4" aria-hidden />
            Re-run reconciliation
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
