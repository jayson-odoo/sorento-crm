'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  AlertCircle,
  CloudUpload,
  Pencil,
  Send,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import {
  useApproveEdition,
  useEditionQuery,
  usePublishEdition,
  useRejectEdition,
  useReopenEdition,
  useSubmitEdition,
} from '../../hooks/useEditions';

/**
 * One Edition, and the single decision available at this point in its life.
 *
 * The header carries EXACTLY ONE primary action, chosen by status - Send for
 * approval, then Approve, then Publish. Reject sits beside it as the outline
 * destructive, because it is the other half of one decision rather than a
 * lesser version of it. Everything else is under the gear.
 *
 * That shape is deliberate and is the pattern the rest of the system uses
 * (purchase requests, complaints, stock inquiries). The Dealer Kit page editor
 * had six equal-weight buttons in a row until it was cut back to two and a
 * gear; this screen starts where that one ended up.
 *
 * Actions that cannot apply are HIDDEN, not disabled. A disabled Approve on a
 * draft invites somebody to hunt for what would enable it, and the answer is
 * "be a different person, later".
 */
export function EditionDetail({ editionId }: { editionId: string }) {
  const { data: edition, isLoading, isError, error } = useEditionQuery(editionId);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState('');

  const submit = useSubmitEdition(editionId);
  const approve = useApproveEdition(editionId);
  const reject = useRejectEdition(editionId);
  const reopen = useReopenEdition(editionId);
  const publish = usePublishEdition(editionId);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (isError || !edition) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="size-4" />
        <AlertTitle>Could not open this edition</AlertTitle>
        <AlertDescription>
          {error instanceof Error ? error.message : 'It does not exist, or you cannot see it.'}
        </AlertDescription>
      </Alert>
    );
  }

  const busy =
    submit.isPending ||
    approve.isPending ||
    reject.isPending ||
    reopen.isPending ||
    publish.isPending;

  return (
    <div className="flex flex-col gap-5">
      <Card>
        {/* Wraps on a phone rather than letting the actions overlap a long
            catalogue name, which is the header bug this repo has fixed on
            every other detail page. */}
        <CardContent className="flex flex-col gap-3 py-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="min-w-0 break-words text-lg font-semibold">{edition.name}</h1>
              <span className={`${STATUS_PILL_BASE} ${statusPillClass(edition.status)}`}>
                {edition.statusLabel}
              </span>
            </div>
            <Link
              href={`/dealer-kit/pages/${edition.pageId}`}
              className="text-sm text-muted-foreground hover:underline"
            >
              {edition.pageName ?? 'Open the catalogue'}
            </Link>
          </div>

          <div className="flex flex-wrap items-center gap-2 sm:justify-end">
            {edition.status === 'draft' && (
              <Button disabled={busy} onClick={() => submit.mutate()}>
                <Send className="size-4" />
                {submit.isPending ? 'Sending' : 'Send for approval'}
              </Button>
            )}

            {edition.status === 'pending_approval' && (
              <>
                <Button disabled={busy} onClick={() => approve.mutate()}>
                  <ThumbsUp className="size-4" />
                  {approve.isPending ? 'Approving' : 'Approve'}
                </Button>
                <Button
                  variant="outline"
                  className="border-destructive text-destructive hover:bg-destructive/10"
                  disabled={busy}
                  onClick={() => {
                    setReason('');
                    setRejectOpen(true);
                  }}
                >
                  <ThumbsDown className="size-4" />
                  Reject
                </Button>
              </>
            )}

            {edition.status === 'approved' && (
              <Button disabled={busy} onClick={() => publish.mutate()}>
                <CloudUpload className="size-4" />
                {publish.isPending ? 'Publishing' : 'Publish'}
              </Button>
            )}

            {edition.status === 'rejected' && (
              <Button disabled={busy} onClick={() => reopen.mutate()}>
                <Pencil className="size-4" />
                {reopen.isPending ? 'Reopening' : 'Reopen for editing'}
              </Button>
            )}

            <DetailActionsMenu ariaLabel="Edition actions">
              <DropdownMenuItem asChild>
                <Link href={`/dealer-kit/pages/${edition.pageId}`}>Open the catalogue</Link>
              </DropdownMenuItem>
            </DetailActionsMenu>
          </div>
        </CardContent>
      </Card>

      {/* The one thing a Designer coming back to rejected work needs to read,
          so it is the first thing on the page and not a field in a grid. */}
      {edition.rejectionReason && (
        <Alert variant="destructive" appearance="light" data-testid="dk-ed-rejection">
          <AlertCircle className="size-4" />
          <AlertTitle>Sent back</AlertTitle>
          <AlertDescription>{edition.rejectionReason}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">History</CardTitle>
        </CardHeader>
        {/* Every row renders even when empty, per the CRUD standard: a section
            that vanishes on missing data reads as a section that failed. */}
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <Fact label="Started" value={formatDateTimeInMalaysia(edition.createdAt)} />
          <Fact
            label="Sent for approval"
            value={
              edition.submittedAt ? formatDateTimeInMalaysia(edition.submittedAt) : 'Not yet'
            }
          />
          <Fact
            label="Approved"
            value={edition.approvedAt ? formatDateTimeInMalaysia(edition.approvedAt) : 'Not yet'}
          />
        </CardContent>
      </Card>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send this back?</DialogTitle>
            <DialogDescription>The designer sees your reason.</DialogDescription>
          </DialogHeader>
          <Textarea
            id="dk-ed-reject-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="What needs to change?"
            rows={4}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectOpen(false)}>
              Cancel
            </Button>
            <Button
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              // The server refuses a blank reason too; this stops the round trip
              // rather than being the only thing standing between a blank
              // rejection and the database.
              disabled={!reason.trim() || reject.isPending}
              onClick={() =>
                reject.mutate(reason.trim(), { onSuccess: () => setRejectOpen(false) })
              }
            >
              {reject.isPending ? 'Sending back' : 'Send back'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm">{value}</span>
    </div>
  );
}
