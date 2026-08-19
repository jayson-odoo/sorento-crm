'use client';

import * as React from 'react';
import { ArrowRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
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
import { formatDateInMalaysia } from '@/lib/helpers';
import { proposalCadenceLabel } from '../lib/scheduleTotals';
import { formatQty } from '../../components/SalesOrderMoney';
import type { RevisionProposal } from '../../../_shared/types/deliverySchedule.types';

/**
 * One product's re-date suggestion per card (section 9.7b), built from its highlighted cells
 * plus the page's own margin note. Every card renders, even with nothing proposed: a reviewer
 * who never sees this section has no way to tell "nothing was found" from "it was not built".
 */
export function DeliveryScheduleRevisionProposals({
  proposals,
  canDecide,
  onAccept,
  onReject,
  pendingIndex,
}: {
  proposals: RevisionProposal[];
  /** False once the version is confirmed, or the reviewer cannot edit it. */
  canDecide: boolean;
  onAccept: (index: number) => void;
  onReject: (index: number) => void;
  /** The index a request is in flight for, so only that card's buttons show pending. */
  pendingIndex: number | null;
}) {
  const [confirming, setConfirming] = React.useState<number | null>(null);
  const confirmingProposal = confirming !== null ? proposals[confirming] : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Re-dating proposals</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {proposals.length === 0 ? (
          <p className="text-sm text-muted-foreground">No re-dating proposed</p>
        ) : (
          proposals.map((proposal, index) => (
            <ProposalCard
              key={`${proposal.item_code ?? proposal.product_id ?? index}-${index}`}
              proposal={proposal}
              canDecide={canDecide}
              pending={pendingIndex === index}
              onAccept={() => setConfirming(index)}
              onReject={() => onReject(index)}
            />
          ))
        )}
      </CardContent>

      <Dialog open={confirming !== null} onOpenChange={(next) => !next && setConfirming(null)}>
        <DialogContent className="w-full max-w-md">
          <DialogHeader>
            <DialogTitle>Re-date this line</DialogTitle>
            <DialogDescription>
              {confirmingProposal &&
                `Re-date ${confirmingProposal.item_code ?? 'this product'}'s ${
                  confirmingProposal.cells.length
                } phase${confirmingProposal.cells.length === 1 ? '' : 's'}? The amendment will ` +
                  'propose ADVANCE per line.'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={() => setConfirming(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => {
                if (confirming !== null) onAccept(confirming);
                setConfirming(null);
              }}
            >
              Accept
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function ProposalCard({
  proposal,
  canDecide,
  pending,
  onAccept,
  onReject,
}: {
  proposal: RevisionProposal;
  canDecide: boolean;
  pending: boolean;
  onAccept: () => void;
  onReject: () => void;
}) {
  const label = proposal.item_code ?? 'This product';
  const firstDate = proposal.cells[0]?.new_date;
  const cadence = proposalCadenceLabel(proposal.cells);
  const title = firstDate
    ? `${label} - re-date ${proposal.cells.length} phase${
        proposal.cells.length === 1 ? '' : 's'
      } from ${formatDateInMalaysia(firstDate)}, ${cadence}`
    : `${label} - re-date ${proposal.cells.length} phase${proposal.cells.length === 1 ? '' : 's'}`;

  return (
    <div className="rounded-lg border border-border p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="break-words text-sm font-medium">{title}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {`From the note on page ${proposal.page_no ?? '?'} and the highlighted cells`}
          </p>
        </div>
        <ProposalStatePill proposal={proposal} />
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-muted-foreground">
              <th className="px-1.5 py-1 text-start font-medium">Phase</th>
              <th className="px-1.5 py-1 text-start font-medium">Qty</th>
              <th className="px-1.5 py-1 text-start font-medium">Delivery date</th>
            </tr>
          </thead>
          <tbody>
            {proposal.cells.map((cell, index) => (
              <tr key={`${cell.phase_id ?? index}`} className="border-t border-border/60">
                <td className="px-1.5 py-1">{cell.phase_label ?? 'Unlabeled phase'}</td>
                <td className="px-1.5 py-1 tabular-nums">
                  {cell.qty ? formatQty(cell.qty) : '—'}
                </td>
                <td className="px-1.5 py-1">
                  <span className="flex items-center gap-1.5 tabular-nums">
                    <span className="text-muted-foreground line-through">
                      {cell.old_date ? formatDateInMalaysia(cell.old_date) : '—'}
                    </span>
                    <ArrowRight className="size-3 shrink-0" aria-hidden />
                    <span className="font-medium">
                      {cell.new_date ? formatDateInMalaysia(cell.new_date) : '—'}
                    </span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {proposal.state === 'proposed' && (
        <div className="mt-3 flex gap-2">
          <Button
            type="button"
            size="sm"
            disabled={!canDecide || pending}
            onClick={onAccept}
          >
            Accept
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!canDecide || pending}
            onClick={onReject}
          >
            Reject
          </Button>
        </div>
      )}
    </div>
  );
}

/**
 * `decided_by` on the wire is a raw user id, not a name - nothing resolves it here, so the
 * pill states the fact without inventing or printing a UUID (no UUIDs in the UI).
 */
function ProposalStatePill({ proposal }: { proposal: RevisionProposal }) {
  if (proposal.state === 'accepted') {
    return (
      <Badge variant="success" appearance="light" className="shrink-0">
        {proposal.decided_at ? `Accepted ${formatDateInMalaysia(proposal.decided_at)}` : 'Accepted'}
      </Badge>
    );
  }
  if (proposal.state === 'rejected') {
    return (
      <Badge variant="secondary" appearance="light" className="shrink-0">
        Rejected
      </Badge>
    );
  }
  return null;
}
