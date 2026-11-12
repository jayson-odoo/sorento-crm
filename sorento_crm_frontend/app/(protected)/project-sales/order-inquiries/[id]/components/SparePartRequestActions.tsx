'use client';

import * as React from 'react';
import Link from 'next/link';
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
import {
  useApproveSparePartRequest,
  useRejectSparePartRequest,
  useReviseSparePartRequest,
  useSubmitSparePartRequest,
} from '../../../_shared/hooks/useSparePartRequest';
import { formatMoneyExact } from '../../../_shared/lib/money';
import { changedFrom, plainNumber } from '../../../_shared/lib/sparePartRequest';
import type {
  OrderInquiryHeaderDetail,
  OrderInquiryWorklistRow,
} from '../../../_shared/types/orderInquiry.types';

/** "line 1 qty 10 to 6": every change the approver made against what was submitted. */
export function approverChanges(rows: OrderInquiryWorklistRow[]): string[] {
  const out: string[] = [];
  rows.forEach((row, index) => {
    const name = row.item_code ? `${row.item_code}` : `line ${index + 1}`;
    if (changedFrom(row.qty, row.submitted_qty)) {
      out.push(`${name} qty ${plainNumber(row.submitted_qty)} to ${plainNumber(row.qty)}`);
    }
    if (changedFrom(row.unit_price, row.submitted_unit_price)) {
      out.push(
        `${name} unit price ${plainNumber(row.submitted_unit_price)} to ${plainNumber(row.unit_price)}`,
      );
    }
  });
  return out;
}

/**
 * SPARE-PART-ORDER-REQUEST: the request's moves, in the OI page's own header card (one main
 * button). The requester: Submit (Edit beside it) on a draft or rejected request, Revise on
 * a raised one purchasing has not started on. The current approver: Approve (a popup that
 * lists their changes) and Reject (a reason is required). Nobody else gets a button.
 */
export function SparePartRequestActions({
  header,
  rows,
}: {
  header: OrderInquiryHeaderDetail;
  rows: OrderInquiryWorklistRow[];
}) {
  const id = header.id;
  const submit = useSubmitSparePartRequest();
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
  const changes = approverChanges(live);

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
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Reject {header.inquiry_no}</DialogTitle>
              <DialogDescription>The requester can change it and submit it again.</DialogDescription>
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
    return (
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outline" asChild>
          <Link href={`/project-sales/order-inquiries/spare-part-requests/${id}/edit`}>Edit</Link>
        </Button>
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
