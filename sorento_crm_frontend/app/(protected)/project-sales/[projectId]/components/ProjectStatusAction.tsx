'use client';

import * as React from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type {
  Status,
  StatusGraph,
  StatusTransition,
} from '@/app/(protected)/system-management/status-graphs/types/statusGraph.types';

export type StatusMove = {
  transitionId: string;
  toStatusId: string;
  /** What the admin called this edge on the status graph, e.g. "PO received". */
  label: string;
  /** The rung it lands on, e.g. "PO Received". */
  toLabel: string;
};

/**
 * The moves a person may fire from where this project stands.
 *
 * Mirrors `available_transitions` in the backend status service, which is the authority:
 * manual edges only (an automatic edge belongs to the engine, so offering it as a button
 * would let a user bypass its conditions), never out of a final rung, never into a
 * deactivated one. Ordered by the edge's own sort order, then by where it lands, so the
 * forward move an admin put first is the one the header offers first.
 *
 * Nothing here invents a lifecycle: an install whose funnel was reshaped in the status
 * graph editor gets its own moves, and a rung with no outgoing edge offers no action at
 * all rather than a button the server would reject.
 */
export function availableStatusMoves(
  graph: StatusGraph | null | undefined,
  fromStatusId?: string | null,
): StatusMove[] {
  if (!graph || !fromStatusId) return [];
  const byId = new Map<string, Status>(graph.statuses.map((status) => [status.id, status]));
  const current = byId.get(fromStatusId);
  if (!current || current.is_terminal) return [];

  return graph.transitions
    .filter(
      (transition) =>
        transition.from_status_id === fromStatusId && transition.trigger_mode === 'manual',
    )
    .map((transition) => ({ transition, target: byId.get(transition.to_status_id) }))
    .filter(
      (pair): pair is { transition: StatusTransition; target: Status } =>
        Boolean(pair.target?.is_active),
    )
    .sort(
      (a, b) =>
        a.transition.sort_order - b.transition.sort_order ||
        a.target.sort_order - b.target.sort_order,
    )
    .map(({ transition, target }) => ({
      transitionId: transition.id,
      toStatusId: target.id,
      label: transition.label,
      toLabel: target.label,
    }));
}

/**
 * The project's one primary action: its next step.
 *
 * One move available names it outright. Several, and the header still shows ONE button,
 * which opens a short list to pick from -- a header with four competing buttons is the
 * same problem as a free dropdown, spelled differently.
 */
export function ProjectStatusAction({
  moves,
  onMove,
  isPending = false,
}: {
  moves: StatusMove[];
  onMove: (toStatusId: string) => void;
  isPending?: boolean;
}) {
  const [choosing, setChoosing] = React.useState(false);

  if (moves.length === 0) return null;
  const only = moves.length === 1 ? moves[0] : null;

  return (
    <>
      <Button
        type="button"
        disabled={isPending}
        onClick={() => (only ? onMove(only.toStatusId) : setChoosing(true))}
      >
        {isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
        {only ? only.label : 'Move stage'}
      </Button>

      {choosing && (
        <Dialog open onOpenChange={(next) => !next && setChoosing(false)}>
          <DialogContent className="max-h-[92vh] w-full max-w-sm overflow-hidden">
            <DialogHeader>
              <DialogTitle>Move stage</DialogTitle>
            </DialogHeader>
            <DialogBody className="max-h-[60vh] space-y-2 overflow-y-auto">
              {moves.map((move) => (
                <Button
                  key={move.transitionId}
                  type="button"
                  variant="outline"
                  className="h-auto w-full justify-start whitespace-normal py-2 text-start"
                  onClick={() => {
                    setChoosing(false);
                    onMove(move.toStatusId);
                  }}
                >
                  <span className="min-w-0 break-words">
                    <span className="block text-sm font-medium">{move.label}</span>
                    <span className="block text-xs text-muted-foreground">
                      {`Moves to ${move.toLabel}`}
                    </span>
                  </span>
                </Button>
              ))}
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setChoosing(false)}>
                Cancel
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
