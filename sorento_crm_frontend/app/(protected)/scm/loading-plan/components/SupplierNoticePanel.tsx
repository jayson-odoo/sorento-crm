'use client';

import { useState } from 'react';
import { Download, LoaderCircle, Send } from 'lucide-react';
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
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import { EM_DASH } from '../../lib/format';
import { useApproveLoadingPlan, usePlanNotices } from '../../hooks/useFulfilment';
import { getNoticeDocumentUrl, type SupplierNotice } from '../../services/fulfilmentService';

/**
 * What the supplier was told, per channel.
 *
 * Rendered even with nothing in it, per the CRUD standard: "no notice has gone out for this
 * plan" is the state Ms Tee most needs to see, and a section that appears only after the first
 * send is a section she has no reason to trust is complete.
 */

const CHANNEL_LABEL: Record<SupplierNotice['channel'], string> = {
  email: 'Email',
  chat: 'Chat',
};

const STATUS_LABEL: Record<SupplierNotice['status'], string> = {
  pending: 'Queued',
  sent: 'Sent',
  failed: 'Failed',
  skipped: 'Not sent',
};

export function SupplierNoticePanel({ planId }: { planId: string }) {
  const notices = usePlanNotices(planId);
  const approve = useApproveLoadingPlan();
  const [confirming, setConfirming] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);

  const rows = notices.data ?? [];
  const alreadySent = rows.length > 0;

  async function openDocument(notice: SupplierNotice) {
    setOpening(notice.id);
    try {
      const { url } = await getNoticeDocumentUrl(notice.id);
      window.open(url, '_blank', 'noopener');
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setOpening(null);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">Supplier notice</h3>
          <p className="text-2xs text-muted-foreground">
            {alreadySent
              ? `Last sent ${(rows[0].created_at && formatDateInMalaysia(rows[0].created_at)) || EM_DASH}`
              : 'Nothing has been sent for this plan yet.'}
          </p>
        </div>
        <Button
          size="sm"
          onClick={() => setConfirming(true)}
          disabled={approve.isPending}
          data-guide-target="scm-send-supplier-notice"
        >
          {approve.isPending ? (
            <LoaderCircle className="size-4 animate-spin" />
          ) : (
            <Send className="size-4" />
          )}
          {alreadySent ? 'Send again' : 'Approve and send'}
        </Button>
      </CardHeader>

      <div className="px-4 pb-4">
        {notices.isLoading ? (
          <Skeleton className="h-20 w-full rounded-lg" />
        ) : !rows.length ? (
          <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
            Approving the plan produces the loading notice and sends it on every channel this
            supplier can be reached on.
          </p>
        ) : (
          <div className="divide-y divide-border rounded-lg border">
            {rows.map((n) => (
              <div
                key={n.id}
                className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium">{CHANNEL_LABEL[n.channel]}</span>
                    <span className={cn(STATUS_PILL_BASE, statusPillClass(n.status))}>
                      {STATUS_LABEL[n.status]}
                    </span>
                    {n.recipient ? (
                      <span className="truncate text-2xs text-muted-foreground" title={n.recipient}>
                        {n.recipient}
                      </span>
                    ) : null}
                  </div>
                  {/* The reason, not just the verdict: "not sent" that does not say why is a
                      dead end, and both of its causes are things a person can fix. */}
                  <p className="mt-0.5 text-2xs text-muted-foreground">
                    {n.last_error || n.status_reason || (
                      n.sent_at ? `Sent ${formatDateInMalaysia(n.sent_at)}` : EM_DASH
                    )}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-2xs text-muted-foreground">
                    {n.line_count} to pack
                    {n.production_line_count ? ` · ${n.production_line_count} to produce` : ''}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!n.has_document || opening === n.id}
                    onClick={() => openDocument(n)}
                  >
                    {opening === n.id ? (
                      <LoaderCircle className="size-4 animate-spin" />
                    ) : (
                      <Download className="size-4" />
                    )}
                    Document
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Send this plan to the supplier?</AlertDialogTitle>
            {/* Confirmed because it leaves the building. Re-sending is the riskier case and is
                the one this wording is for. */}
            <AlertDialogDescription>
              {alreadySent
                ? 'This supplier has already been sent a notice for this plan. Sending again produces a second notice and a second email.'
                : 'The supplier will be emailed the loading notice and the items that need production.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setConfirming(false);
                approve.mutate(planId);
              }}
            >
              Send
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
