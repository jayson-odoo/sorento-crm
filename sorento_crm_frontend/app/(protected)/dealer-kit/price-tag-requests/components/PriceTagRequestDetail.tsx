'use client';

/**
 * CRM price tag request detail view.
 *
 * Phase 1: mock data. Shows request header, status actions, lines table with
 * resolved prices, and PO attachments.
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
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
import { Skeleton } from '@/components/ui/skeleton';
import RecordNavigation from '@/components/common/RecordNavigation';
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

interface Props {
  requestId: string;
}

export default function PriceTagRequestDetail({ requestId }: Props) {
  const router = useRouter();
  const [request, setRequest] = useState<PriceTagRequestDetailType | null>(
    null,
  );
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
      // Refetch
      const data = await getPriceTagRequest(requestId);
      setRequest(data);
    } catch {
      toast.error('Failed to claim request');
    } finally {
      setActionLoading(false);
    }
  }, [requestId]);

  const handleTransition = useCallback(
    async (action: string, label: string) => {
      setActionLoading(true);
      try {
        await transitionPriceTagRequest(requestId, action);
        toast.success(`${label}`);
        const data = await getPriceTagRequest(requestId);
        setRequest(data);
      } catch {
        toast.error(`Failed: ${label}`);
      } finally {
        setActionLoading(false);
      }
    },
    [requestId],
  );

  const handleExport = useCallback(async () => {
    setExportLoading(true);
    try {
      const result = await exportTagSheet(requestId);
      toast.success(
        `PDF export queued. Check My Downloads for "${result.filename}".`,
      );
      // Refetch to reflect status change (approved -> ready on first export).
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

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-60 w-full" />
      </div>
    );
  }

  if (!request) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Request not found.</p>
        <Button
          variant="link"
          onClick={() => router.push('/dealer-kit/price-tag-requests')}
          className="mt-2"
        >
          Back to list
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Back + navigation */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push('/dealer-kit/price-tag-requests')}
        >
          <ArrowLeft className="size-4 mr-1" /> Back to list
        </Button>
        <RecordNavigation
          basePath="/dealer-kit/price-tag-requests"
          prevId={null}
          nextId={null}
          ariaLabel="price tag request"
        />
      </div>

      {/* Header card */}
      <Card>
        <CardContent className="pt-4 space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-semibold">{request.doc_number}</h2>
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${priceTagStatusPillClass(request.status)}`}
              >
                {priceTagStatusLabel(request.status)}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground block">Debtor</span>
              <p className="font-medium">{request.debtor_name}</p>
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
            {request.promotion_name && (
              <div>
                <span className="text-muted-foreground block">Promotion</span>
                <p className="font-medium">{request.promotion_name}</p>
              </div>
            )}
            <div>
              <span className="text-muted-foreground block">Deadline</span>
              <p className="font-medium">
                {formatDate(new Date(request.needed_by_date))}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground block">Created</span>
              <p className="font-medium">
                {formatDateTimeInMalaysia(request.created_at)}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground block">Assigned to</span>
              <p className="font-medium">
                {request.assigned_to_name ?? 'Unclaimed'}
              </p>
            </div>
          </div>

          {request.notes && (
            <div>
              <span className="text-sm text-muted-foreground block">Notes</span>
              <p className="text-sm mt-1">{request.notes}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Status actions */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap gap-2">
            {request.status === 'new' && !request.assigned_to_id && (
              <Button
                onClick={handleClaim}
                disabled={actionLoading}
                size="sm"
              >
                {actionLoading ? (
                  <Loader2 className="size-4 mr-1 animate-spin" />
                ) : (
                  <UserPlus className="size-4 mr-1" />
                )}
                Claim
              </Button>
            )}
            {(request.status === 'designing' ||
              request.status === 'changes_requested') && (
              <Button
                variant="primary"
                size="sm"
                onClick={() =>
                  router.push(
                    `/dealer-kit/price-tag-requests/${requestId}/design`,
                  )
                }
              >
                <Palette className="size-4 mr-1" />
                Design Tags
              </Button>
            )}
            {request.status === 'designing' && (
              <Button
                onClick={() =>
                  handleTransition('mark_proof_ready', 'Proof marked as ready')
                }
                disabled={actionLoading}
                size="sm"
                variant="outline"
              >
                {actionLoading ? (
                  <Loader2 className="size-4 mr-1 animate-spin" />
                ) : (
                  <Eye className="size-4 mr-1" />
                )}
                Mark Proof Ready
              </Button>
            )}
            {(request.status === 'approved' ||
              request.status === 'ready') && (
              <Button
                onClick={handleExport}
                disabled={exportLoading || actionLoading}
                size="sm"
              >
                {exportLoading ? (
                  <Loader2 className="size-4 mr-1 animate-spin" />
                ) : (
                  <Download className="size-4 mr-1" />
                )}
                Export PDF
              </Button>
            )}
            {!['void', 'ready', 'rejected'].includes(request.status) && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setVoidDialogOpen(true)}
                disabled={actionLoading}
              >
                <XCircle className="size-4 mr-1" />
                Void
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Lines table */}
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
                        <span className="truncate block max-w-[200px]" title={line.name}>
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

      {/* PO Attachments */}
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-base">PO Attachments</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          {request.attachments.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              No PO attachments uploaded.
            </p>
          ) : (
            <div className="space-y-1">
              {request.attachments.map((att) => (
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

      {/* Void confirmation dialog */}
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
