'use client';

/**
 * CRM price tag request detail view.
 *
 * The same page as every other form detail in this app (D50): breadcrumb as the
 * way back, the document number as the heading with the status pill and the
 * record metadata beside it, ONE primary CTA followed by the gear menu and the
 * prev/next chevrons, then the request, its lines, its PO attachments and its
 * proof as cards.
 *
 * Which action is primary and which are secondary is `priceTagActions`, so the
 * page never has to decide twice.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Download,
  Eye,
  FileText,
  Loader2,
  Palette,
  UserPlus,
  XCircle,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import PriceTagRequestNavigation from './PriceTagRequestNavigation';
import {
  priceTagStatusLabel,
  priceTagStatusPillClass,
} from '@/lib/price-tag-status';
import { formatDate, formatDateTimeInMalaysia } from '@/lib/helpers';
import {
  getPriceTagRequest,
  claimPriceTagRequest,
  transitionPriceTagRequest,
  exportTagSheet,
  type PriceTagRequestDetail as PriceTagRequestDetailType,
} from '../../services/priceTagRequestService';
import {
  priceTagActions,
  type PriceTagAction,
  type PriceTagActionSpec,
} from './priceTagRequestActions';

const STATUS_PILL_BASE =
  'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold';

const ACTION_ICON: Record<PriceTagAction, typeof UserPlus> = {
  claim: UserPlus,
  design: Palette,
  mark_proof_ready: Eye,
  export: Download,
  void: XCircle,
};

/** What the proof section says at each status. */
function proofSummary(status: string): string {
  switch (status) {
    case 'new':
    case 'draft':
      return 'Nothing has been designed yet. Claim the request and design its tags.';
    case 'designing':
      return 'The tags are being designed. Mark the proof ready to send it to the salesperson.';
    case 'proof_ready':
      return 'The proof is with the salesperson, waiting to be approved.';
    case 'changes_requested':
      return 'The salesperson asked for changes. Design the tags again and mark a new proof ready.';
    case 'approved':
      return 'The proof was approved. Export the PDF to print it.';
    case 'ready':
      return 'The PDF has been exported. Look for it in My Downloads.';
    case 'rejected':
      return 'The request was rejected, so there is no proof to show.';
    case 'void':
      return 'The request was voided, so there is no proof to show.';
    default:
      return 'No proof has been produced for this request.';
  }
}

interface Props {
  requestId: string;
}

export default function PriceTagRequestDetail({ requestId }: Props) {
  const router = useRouter();
  const [request, setRequest] = useState<PriceTagRequestDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [voidDialogOpen, setVoidDialogOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getPriceTagRequest(requestId)
      .then((data) => {
        if (cancelled) return;
        setRequest(data);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [requestId]);

  const handleClaim = useCallback(async () => {
    setActionLoading(true);
    try {
      await claimPriceTagRequest(requestId);
      toast.success('Request claimed');
      const data = await getPriceTagRequest(requestId);
      setRequest(data);
    } catch {
      toast.error('Failed to claim request');
    } finally {
      setActionLoading(false);
    }
  }, [requestId]);

  const handleMarkProofReady = useCallback(async () => {
    setActionLoading(true);
    try {
      await transitionPriceTagRequest(requestId, 'mark_proof_ready');
      toast.success('Proof marked as ready');
      const data = await getPriceTagRequest(requestId);
      setRequest(data);
    } catch {
      toast.error('Failed to mark the proof ready');
    } finally {
      setActionLoading(false);
    }
  }, [requestId]);

  const handleExport = useCallback(async () => {
    setExportLoading(true);
    try {
      const result = await exportTagSheet(requestId);
      toast.success(
        `PDF export queued. Check My Downloads for "${result.filename}".`,
      );
      // Refetch to reflect the status change (approved -> ready on first export).
      const data = await getPriceTagRequest(requestId);
      setRequest(data);
    } catch {
      toast.error('Failed to export PDF');
    } finally {
      setExportLoading(false);
    }
  }, [requestId]);

  const handleVoid = useCallback(async () => {
    setActionLoading(true);
    try {
      await transitionPriceTagRequest(requestId, 'void');
      toast.success('Request voided');
      setVoidDialogOpen(false);
      router.push('/dealer-kit/price-tag-requests');
    } catch {
      toast.error('Failed to void request');
    } finally {
      setActionLoading(false);
    }
  }, [requestId, router]);

  const openDesigner = useCallback(() => {
    router.push(`/dealer-kit/price-tag-requests/${requestId}/design`);
  }, [requestId, router]);

  const runAction = useCallback(
    (action: PriceTagAction) => {
      if (action === 'claim') return void handleClaim();
      if (action === 'design') return openDesigner();
      if (action === 'mark_proof_ready') return void handleMarkProofReady();
      if (action === 'export') return void handleExport();
      setVoidDialogOpen(true);
    },
    [handleClaim, openDesigner, handleMarkProofReady, handleExport],
  );

  const actions: PriceTagActionSpec[] = useMemo(
    () => (request ? priceTagActions(request.status, request.assigned_to_id) : []),
    [request],
  );
  const primary = actions[0] ?? null;
  const secondary = actions.slice(1);

  const busy = actionLoading || exportLoading;

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-60 w-full" />
      </div>
    );
  }

  if (!request) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Price tag request not found</p>
        <Button
          variant="outline"
          onClick={() => router.push('/dealer-kit/price-tag-requests')}
          className="mt-4"
        >
          Back to Price Tag Requests
        </Button>
      </div>
    );
  }

  const PrimaryIcon = primary ? ACTION_ICON[primary.action] : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1 min-w-0">
          <h1 className="text-2xl font-bold break-words">
            Price Tag Request - {request.doc_number}
          </h1>
          <p className="text-sm text-muted-foreground">
            Created: {formatDateTimeInMalaysia(request.created_at)}
            {request.status && (
              <>
                {' · '}
                <span
                  className={`${STATUS_PILL_BASE} ${priceTagStatusPillClass(request.status)}`}
                >
                  {priceTagStatusLabel(request.status)}
                </span>
              </>
            )}
          </p>
          <p className="text-sm text-muted-foreground">
            Needed by:{' '}
            {request.needed_by_date
              ? formatDate(new Date(request.needed_by_date))
              : '-'}
            {' · '}
            Assigned to: {request.assigned_to_name ?? 'Unclaimed'}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap sm:justify-end">
          {primary && (
            <Button
              variant="primary"
              size="sm"
              disabled={busy}
              onClick={() => runAction(primary.action)}
              data-testid="price-tag-primary-cta"
            >
              {busy ? (
                <Loader2 className="size-4 mr-1 animate-spin" />
              ) : (
                PrimaryIcon && <PrimaryIcon className="size-4 mr-1" />
              )}
              {primary.label}
            </Button>
          )}
          {secondary.length > 0 && (
            <DetailActionsMenu ariaLabel="Price tag request actions">
              {secondary.map((spec) => {
                const Icon = ACTION_ICON[spec.action];
                return (
                  <DropdownMenuItem
                    key={spec.action}
                    disabled={busy}
                    className={
                      spec.destructive
                        ? 'text-destructive focus:text-destructive'
                        : undefined
                    }
                    onSelect={(event) => {
                      event.preventDefault();
                      runAction(spec.action);
                    }}
                  >
                    <Icon className="size-4" />
                    {spec.label}
                  </DropdownMenuItem>
                );
              })}
            </DetailActionsMenu>
          )}
          <PriceTagRequestNavigation requestId={requestId} />
        </div>
      </div>

      {/* Request */}
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-base">Request</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground block">Debtor</span>
              {/* A portal draft may carry neither (D48a). */}
              <p className="font-medium">{request.debtor_name ?? '-'}</p>
              {request.debtor_code && (
                <p className="text-xs text-muted-foreground">
                  {request.debtor_code}
                </p>
              )}
            </div>
            <div>
              <span className="text-muted-foreground block">Salesperson</span>
              <p className="font-medium">{request.contact_name ?? '-'}</p>
            </div>
            <div>
              <span className="text-muted-foreground block">Promotion</span>
              <p className="font-medium">{request.promotion_name ?? '-'}</p>
            </div>
          </div>
          <div className="mt-4">
            <span className="text-sm text-muted-foreground block">Notes</span>
            <p className="text-sm mt-1">
              {request.notes ? (
                request.notes
              ) : (
                <span className="text-muted-foreground">
                  The salesperson left no notes.
                </span>
              )}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Lines */}
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-base">
            Lines ({request.lines.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          {request.lines.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              No lines in this request.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">Type</th>
                    <th className="py-2 pr-3 font-medium">Code</th>
                    <th className="py-2 pr-3 font-medium">Name</th>
                    <th className="py-2 pr-3 font-medium text-right">Qty</th>
                    <th className="py-2 pr-3 font-medium text-right">
                      List Price
                    </th>
                    <th className="py-2 pr-3 font-medium text-right">
                      Sell Price
                    </th>
                    <th className="py-2 font-medium">Accessories</th>
                  </tr>
                </thead>
                <tbody>
                  {request.lines.map((line) => (
                    <tr key={line.id} className="border-b last:border-b-0">
                      <td className="py-2 pr-3">
                        <Badge variant="secondary" className="text-xs">
                          {line.line_type === 'product' ? 'Product' : 'Set'}
                        </Badge>
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs">
                        {line.code}
                      </td>
                      <td className="py-2 pr-3">
                        <span
                          className="truncate block max-w-[200px]"
                          title={line.name}
                        >
                          {line.name}
                        </span>
                        {line.alternatives.length > 0 && (
                          <span className="text-xs text-muted-foreground">
                            +{line.alternatives.length} alt
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-3 text-right">{line.quantity}</td>
                      <td className="py-2 pr-3 text-right">
                        {line.list_price != null
                          ? `RM ${line.list_price.toFixed(2)}`
                          : '-'}
                      </td>
                      <td className="py-2 pr-3 text-right">
                        {line.show_promo_price && line.sell_price != null ? (
                          <span className="text-green-700 font-medium">
                            RM {line.sell_price.toFixed(2)}
                          </span>
                        ) : (
                          '-'
                        )}
                        {line.marketing_price_override != null && (
                          <span className="block text-xs text-amber-600">
                            Override: RM{' '}
                            {line.marketing_price_override.toFixed(2)}
                          </span>
                        )}
                      </td>
                      <td className="py-2 text-muted-foreground text-xs">
                        {line.included_accessories ?? '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* PO attachments */}
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-base">PO Attachments</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          {(request.attachments?.length ?? 0) === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              No PO attachments uploaded.
            </p>
          ) : (
            <div className="space-y-1">
              {(request.attachments ?? []).map((att) => (
                <div
                  key={att.id}
                  className="flex items-center justify-between text-sm px-2 py-1.5 bg-muted rounded"
                >
                  <div className="flex items-center min-w-0">
                    <FileText className="size-4 mr-2 text-muted-foreground shrink-0" />
                    <span className="truncate" title={att.filename}>
                      {att.filename}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground ml-2 shrink-0">
                    {formatDateTimeInMalaysia(att.created_at)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Proof */}
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-base">Proof</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <p className="text-sm text-muted-foreground">
            {proofSummary(request.status)}
          </p>
          {actions.some((spec) => spec.action === 'design') && (
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={openDesigner}
            >
              <Palette className="size-4 mr-1" />
              Open the designer
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Void confirmation */}
      <AlertDialog open={voidDialogOpen} onOpenChange={setVoidDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Void this request?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently void request {request.doc_number}. This
              action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleVoid}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Void
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
