'use client';

import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
  /** Terminal rungs (Lost, Dormant) are exits, never the happy path. */
  toIsTerminal: boolean;
};

/**
 * The forward move, and everything else.
 *
 * The happy path is the FIRST non-terminal move in the admin's own sort order. That is the
 * step the person came to take, so it is the one button in the header; exits and side moves
 * go behind the gear, where a deliberate action belongs.
 *
 * A funnel whose only remaining moves are terminal (nothing forward left) still gets a
 * primary button, because "there is a next step but we are hiding it" would be worse than
 * naming the exit.
 */
export function splitStatusMoves(moves: StatusMove[]): {
  primary: StatusMove | null;
  secondary: StatusMove[];
} {
  if (moves.length === 0) return { primary: null, secondary: [] };
  const forward = moves.find((move) => !move.toIsTerminal) ?? moves[0];
  return {
    primary: forward,
    secondary: moves.filter((move) => move.transitionId !== forward.transitionId),
  };
}

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
      toIsTerminal: Boolean(target.is_terminal),
    }));
}

/**
 * The project's one primary action: its next step, named.
 *
 * It used to open a dialog listing every legal move - "Register with developer", "PO
 * received", "Mark lost", "Mark dormant" - which makes the commonest action a decision
 * between four, and puts marking a pursuit LOST one careless click from advancing it. The
 * header now fires the forward move directly. Exits live behind the gear (see
 * `splitStatusMoves`), so choosing one is deliberate.
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
  const { primary } = splitStatusMoves(moves);
  if (!primary) return null;

  return (
    <Button type="button" disabled={isPending} onClick={() => onMove(primary.toStatusId)}>
      {isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {primary.label}
    </Button>
  );
}
