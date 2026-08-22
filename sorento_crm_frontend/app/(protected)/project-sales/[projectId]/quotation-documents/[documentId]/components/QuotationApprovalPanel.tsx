'use client';

import * as React from 'react';
import { ShieldAlert, ShieldCheck, Undo2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useHasPermission } from '@/hooks/usePermissions';
import type { StatusGraph } from '@/app/(protected)/system-management/status-graphs/types/statusGraph.types';
import {
  ProjectStatusAction,
  availableStatusMoves,
  type StatusMove,
} from '../../../components/ProjectStatusAction';
import type { QuotationDocument } from '../../../../_shared/services/quotationDocumentService';

/** The grant a manager needs to decide a below-floor quotation. */
export const APPROVE_PERMISSION = 'projects.quotations.approve';

/**
 * The two rungs a salesperson may move to themselves.
 *
 * Everything else on the graph is owned by an act with its own rules: approving and rejecting
 * carry the permission and (for a rejection) the required reason, and `issued` is stamped by
 * issuing rather than claimed. The server refuses the rest on the generic move route, so
 * filtering here only keeps the screen from offering a button the server would reject.
 */
const SELF_SERVE_KEYS = new Set(['pending_approval', 'draft']);

/**
 * Whether this quotation is currently blocked from being issued.
 *
 * Exported because the header's Issue CTA is gated on the same answer, and two expressions
 * for one rule is how a disabled button ends up disagreeing with the sentence beside it.
 */
export function isBlockedByApproval(document: QuotationDocument): boolean {
  return Boolean(document.requires_approval) && document.approval_status_key !== 'approved';
}

/**
 * The moves this person may fire, in the shared helpers' own shape.
 *
 * `availableStatusMoves` is the authority on WHICH edges exist (it mirrors the backend's
 * `available_transitions` exactly), so nothing here invents a lifecycle; this only drops the
 * edges that belong to a dedicated act. A document that has never needed a manager carries no
 * status at all, and then it sits at the graph's initial rung without having had to say so.
 */
export function approvalMoves(
  graph: StatusGraph | null | undefined,
  document: QuotationDocument,
): StatusMove[] {
  if (!graph) return [];
  const from =
    document.approval_status_id ?? graph.statuses.find((status) => status.is_initial)?.id ?? null;
  const keyById = new Map(graph.statuses.map((status) => [status.id, status.key]));
  return availableStatusMoves(graph, from).filter((move) =>
    SELF_SERVE_KEYS.has(keyById.get(move.toStatusId) ?? ''),
  );
}

function BlockLine({ children }: { children: React.ReactNode }) {
  return <p className="min-w-0 text-sm text-foreground">{children}</p>;
}

/**
 * The price-floor approval gate, stated on the screen it blocks.
 *
 * Renders NOTHING at all for the ordinary quotation - no line below its floor and no position
 * on the approval graph - so the common case gains no chrome and no extra step. That is the
 * whole point of the gate: it exists for the quotation that discounts past the floor, and it
 * is invisible to every other one.
 *
 * When it does appear it always names the reason AND offers the next action as a click, the
 * same shape the unsigned-quotation gate already has. A block that only says no is a dead end,
 * and the salesperson's next move (asking a manager) is one press away rather than a message
 * outside the system.
 */
export function QuotationApprovalPanel({
  document,
  graph,
  canEdit,
  onMove,
  onApprove,
  onReject,
  isMoving = false,
  isDeciding = false,
}: {
  document: QuotationDocument;
  graph: StatusGraph | null | undefined;
  /** Whether this reader may edit the project this quotation belongs to. */
  canEdit: boolean;
  onMove: (toStatusId: string) => void;
  onApprove: () => void;
  onReject: (reason: string) => Promise<void> | void;
  isMoving?: boolean;
  isDeciding?: boolean;
}) {
  const [rejecting, setRejecting] = React.useState(false);
  const [reason, setReason] = React.useState('');
  const canApprove = useHasPermission(APPROVE_PERMISSION);

  const statusKey = document.approval_status_key ?? null;
  const belowFloor = document.below_floor_line_count ?? 0;
  const blocked = isBlockedByApproval(document);
  const moves = approvalMoves(graph, document);

  // The panel is about the floor, so with nothing below the floor there is nothing to say -
  // including on a quotation that was approved once and has since been re-priced back above it.
  // A quotation that never discounted that far never sees this panel at all.
  if (belowFloor === 0) return null;

  const priced =
    belowFloor === 1
      ? 'One line is priced below its floor'
      : `${belowFloor} lines are priced below their floor`;

  const tone = blocked
    ? 'border-amber-500/40 bg-amber-500/5'
    : 'border-emerald-500/40 bg-emerald-500/5';

  return (
    <div className={`rounded-lg border px-4 py-3 ${tone}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 gap-2.5">
          {blocked ? (
            <ShieldAlert className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden />
          ) : (
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden />
          )}
          <div className="min-w-0 space-y-1">
            {statusKey === 'pending_approval' && (
              <BlockLine>
                {`${priced}, so this quotation is with a manager for approval. It cannot be sent to the customer until they decide.`}
              </BlockLine>
            )}
            {statusKey === 'rejected' && (
              <>
                <BlockLine>
                  A manager sent this back. Re-price the lines below the floor, then ask again.
                </BlockLine>
                {document.approval_rejected_reason && (
                  <p className="min-w-0 break-words text-sm text-muted-foreground">
                    {`Their reason: ${document.approval_rejected_reason}`}
                  </p>
                )}
              </>
            )}
            {statusKey === 'approved' && (
              <BlockLine>
                {`${priced}, and a manager has approved it. It can be issued.`}
              </BlockLine>
            )}
            {blocked && statusKey !== 'pending_approval' && statusKey !== 'rejected' && (
              <BlockLine>
                {`${priced}, so this quotation needs a manager's approval before it can be sent to the customer.`}
              </BlockLine>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
          {canEdit && (
            <ProjectStatusAction moves={moves} onMove={onMove} isPending={isMoving} />
          )}
          {statusKey === 'pending_approval' && canApprove && (
            <>
              <Button
                type="button"
                variant="outline"
                disabled={isDeciding}
                onClick={() => setRejecting(true)}
              >
                <Undo2 className="size-4" aria-hidden />
                Reject
              </Button>
              <Button type="button" disabled={isDeciding} onClick={onApprove}>
                <ShieldCheck className="size-4" aria-hidden />
                Approve
              </Button>
            </>
          )}
        </div>
      </div>

      <Dialog
        open={rejecting}
        onOpenChange={(next) => {
          setRejecting(next);
          if (!next) setReason('');
        }}
      >
        <DialogContent className="max-h-[92vh] w-full max-w-md overflow-hidden">
          <DialogHeader>
            <DialogTitle>Send this back</DialogTitle>
            <DialogDescription>
              The salesperson sees your reason on the quotation and re-prices from there.
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              await onReject(reason.trim());
              setRejecting(false);
              setReason('');
            }}
          >
            <DialogBody className="max-h-[65vh] space-y-2 overflow-y-auto">
              <Label htmlFor="quotation-reject-reason">
                Why <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="quotation-reject-reason"
                rows={4}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="e.g. the WC suite has to come back to at least RM 240"
              />
            </DialogBody>
            <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
              <Button type="button" variant="outline" onClick={() => setRejecting(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!reason.trim() || isDeciding}>
                Send it back
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
