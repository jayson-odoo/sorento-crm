'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { LoaderCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/lib/toast';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import {
  useApproveSparePartRequest,
  useRejectSparePartRequest,
  useReviseSparePartRequest,
  useSubmitSparePartRequest,
} from '../../../_shared/hooks/useSparePartRequest';
import { formatMoneyExact } from '../../../_shared/lib/money';
import {
  SPARE_PART_REQUESTS_PATH,
  changedFrom,
  isPreApproval,
} from '../../../_shared/lib/sparePartRequest';
import { SPARE_PART_REQUESTS_KEY } from '../../../_shared/hooks/useSparePartRequest';
import { formatInquiryQty } from '../../../_shared/lib/orderInquiryWorklist';
import type {
  OrderInquiryHeaderDetail,
  OrderInquiryWorklistRow,
} from '../../../_shared/types/orderInquiry.types';

function photoCount(count: number, verb: string): string {
  return `${count} photo${count === 1 ? '' : 's'} ${verb}`;
}

/** "SP-SEAL-40 qty 10 to 6", "SP-HINGE 1 photo added": every change the approver made
 *  against what was submitted, per line. */
export function approverChanges(
  rows: OrderInquiryWorklistRow[],
  currency?: string | null,
): string[] {
  const out: string[] = [];
  rows.forEach((row, index) => {
    const name = row.item_code ? `${row.item_code}` : `line ${index + 1}`;
    if (changedFrom(row.qty, row.submitted_qty)) {
      out.push(`${name} qty ${formatInquiryQty(row.submitted_qty)} to ${formatInquiryQty(row.qty)}`);
    }
    if (changedFrom(row.unit_price, row.submitted_unit_price)) {
      out.push(
        `${name} unit price ${formatMoneyExact(row.submitted_unit_price, currency)} to ${formatMoneyExact(
          row.unit_price,
          currency,
        )}`,
      );
    }
    const added = row.photo_changes?.added ?? 0;
    const removed = row.photo_changes?.removed ?? 0;
    if (added > 0) out.push(`${name} ${photoCount(added, 'added')}`);
    if (removed > 0) out.push(`${name} ${photoCount(removed, 'removed')}`);
  });
  return out;
}

/** What the actions read off the request: the OI header on the OI page, the request's own
 *  detail on its record page (`SparePartRequestRecord`). */
export type SparePartActionsHeader = Pick<
  OrderInquiryHeaderDetail,
  'id' | 'state' | 'currency' | 'can_decide' | 'can_edit' | 'can_revise'
> & { inquiry_no?: string | null };

/**
 * SPARE-PART-ORDER-REQUEST: the request's moves, in the header card (one main button). The
 * requester: Submit (Edit beside it) on a draft or rejected request, Edit alone while it is
 * pending approval (saving restarts approval, G5), Revise on a raised one purchasing has not
 * started on. The current approver: Approve (a popup that lists their changes) and Reject (a
 * reason is required). Nobody else gets a button.
 */
export function SparePartRequestActions({
  header,
  rows,
}: {
  header: SparePartActionsHeader;
  rows: OrderInquiryWorklistRow[];
}) {
  const id = header.id;
  const router = useRouter();
  const submit = useSubmitSparePartRequest();
  // Delete draft (D7): a server-deferred countdown with Cancel, never a confirm.
  const deletion = useDeferredAction({
    actionKey: 'spare_part_request.delete',
    entityType: 'spare_part_request',
    entityId: id,
    verb: 'Deleting',
    subject: header.inquiry_no ?? 'this request',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Request deleted',
    invalidateKeys: [['order-inquiry-headers'], [SPARE_PART_REQUESTS_KEY]],
    onCommitted: () => router.push(SPARE_PART_REQUESTS_PATH),
  });
  const approve = useApproveSparePartRequest(id);
  const reject = useRejectSparePartRequest(id);
  const revise = useReviseSparePartRequest(id);
  const [approveOpen, setApproveOpen] = React.useState(false);
  const [rejectOpen, setRejectOpen] = React.useState(false);
  const [note, setNote] = React.useState('');
  const [reason, setReason] = React.useState('');
  const [touched, setTouched] = React.useState(false);

  const live = rows.filter((row) => row.state !== 'cancelled');
  const going = live.filter((row) => Number(row.qty ?? 0) > 0);
  const total = going.reduce((sum, row) => sum + Number(row.line_total ?? 0), 0).toFixed(4);
  const changes = approverChanges(live, header.currency);

  if (header.can_decide) {
    return (
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            setReason('');
            setTouched(false);
            setRejectOpen(true);
          }}
        >
          Reject
        </Button>
        <Button
          size="sm"
          onClick={() => {
            setNote('');
            setApproveOpen(true);
          }}
        >
          Approve
        </Button>

        <Dialog open={approveOpen} onOpenChange={setApproveOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Approve {header.inquiry_no}</DialogTitle>
              <DialogDescription>
                {going.length} line{going.length === 1 ? '' : 's'},{' '}
                {formatMoneyExact(total, header.currency)}.
              </DialogDescription>
            </DialogHeader>
            <DialogBody className="space-y-3">
              {changes.length ? (
                <div className="space-y-1">
                  <p className="text-sm font-medium">Your changes</p>
                  <ul className="list-disc space-y-0.5 ps-5 text-sm">
                    {changes.map((change) => (
                      <li key={change}>{change}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No changes to the submitted lines.</p>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="spr-approve-note">Note</Label>
                <Textarea
                  id="spr-approve-note"
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  rows={2}
                />
              </div>
            </DialogBody>
            <DialogFooter>
              <Button variant="outline" onClick={() => setApproveOpen(false)} disabled={approve.isPending}>
                Back
              </Button>
              <Button
                onClick={() =>
                  approve.mutate(note.trim() || undefined, { onSuccess: () => setApproveOpen(false) })
                }
                disabled={approve.isPending}
              >
                {approve.isPending ? <LoaderCircle className="size-4 animate-spin" /> : null}
                Approve
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
          <DialogContent aria-describedby={undefined}>
            <DialogHeader>
              <DialogTitle>Reject {header.inquiry_no}</DialogTitle>
            </DialogHeader>
            <DialogBody className="space-y-1.5">
              <Label htmlFor="spr-reject-reason">
                Reason <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="spr-reject-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={3}
                autoFocus
              />
              {touched && !reason.trim() ? (
                <p className="text-2xs text-destructive">A reason is required to reject.</p>
              ) : null}
            </DialogBody>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRejectOpen(false)} disabled={reject.isPending}>
                Back
              </Button>
              <Button
                variant="destructive"
                disabled={reject.isPending}
                onClick={() => {
                  setTouched(true);
                  if (!reason.trim()) return;
                  reject.mutate(reason.trim(), { onSuccess: () => setRejectOpen(false) });
                }}
              >
                {reject.isPending ? <LoaderCircle className="size-4 animate-spin" /> : null}
                Reject
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  if (header.can_edit) {
    if (deletion.countdown) return <div className="flex items-center gap-2">{deletion.countdown}</div>;
    const editLink = (
      <Button size="sm" variant="outline" asChild>
        <Link href={`${SPARE_PART_REQUESTS_PATH}/${id}/edit`}>Edit</Link>
      </Button>
    );
    // G5: while it waits for approval the requester may still edit it; nothing else.
    if (header.state === 'pending_approval' || !isPreApproval(header.state)) {
      return <div className="flex items-center gap-2">{editLink}</div>;
    }
    return (
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="ghost"
          disabled={deletion.isBlocked}
          onClick={() => deletion.start()}
        >
          Delete draft
        </Button>
        {editLink}
        <Button size="sm" onClick={() => submit.mutate(id, { onError: (e: Error) => toast.error(e.message) })} disabled={submit.isPending}>
          {submit.isPending ? <LoaderCircle className="size-4 animate-spin" /> : null}
          Submit
        </Button>
      </div>
    );
  }

  if (header.can_revise) {
    return (
      <Button size="sm" variant="outline" onClick={() => revise.mutate()} disabled={revise.isPending}>
        Revise
      </Button>
    );
  }

  return null;
}

export default SparePartRequestActions;
