import type { MockStatus, MockTransition } from './documentMocks';

/**
 * The moves a person may fire from where this quotation stands, and which one is the button.
 *
 * The client: "our call to action for quotation is move to next stage ma, which should be based
 * on our status graph lo". So the primary CTA is not a hardcoded "Issue R3" - it is whatever the
 * graph says comes next, exactly as the project header already works
 * (`ProjectStatusAction.splitStatusMoves`).
 *
 * The ranking rule is copied deliberately rather than re-invented: the happy path is the first
 * move that ADVANCES - non-terminal, landing on a LATER rung than the current one. Ranking on
 * the target rung's position needs no extra data and cannot be broken by an admin who leaves
 * every edge's sort order at zero, which is how the project header once ended up offering "Back
 * to identified" as the obvious next step.
 *
 * Backward and terminal moves are real and stay available, behind the gear, because a correction
 * or an exit should be deliberate.
 *
 * Phase 2 deletes this file and calls the real `availableStatusMoves` against the fetched graph.
 */
export type DocumentMove = {
  transitionId: string;
  toStatusId: string;
  label: string;
  toLabel: string;
  toIsTerminal: boolean;
  isForward: boolean;
};

export function documentMoves(
  statuses: MockStatus[],
  transitions: MockTransition[],
  fromStatusId: string,
): DocumentMove[] {
  const byId = new Map(statuses.map((status) => [status.id, status]));
  const current = byId.get(fromStatusId);
  // A terminal rung offers nothing rather than a button the server would refuse.
  if (!current || current.is_terminal) return [];

  return transitions
    .filter((transition) => transition.from_status_id === fromStatusId)
    .flatMap((transition) => {
      const target = byId.get(transition.to_status_id);
      if (!target) return [];
      return [
        {
          transitionId: transition.id,
          toStatusId: target.id,
          label: transition.label,
          toLabel: target.label,
          toIsTerminal: target.is_terminal,
          isForward: target.sort_order > current.sort_order,
        },
      ];
    });
}

export function splitDocumentMoves(moves: DocumentMove[]): {
  primary: DocumentMove | null;
  secondary: DocumentMove[];
} {
  if (moves.length === 0) return { primary: null, secondary: [] };
  const forward =
    // Advance along the funnel.
    moves.find((move) => !move.toIsTerminal && move.isForward) ??
    // A FORWARD terminal rung is still the next step. Won, Accepted and Delivered are ends,
    // and naming one beats offering a correction: with "Accepted" terminal and "Back to draft"
    // open, preferring merely-non-terminal made "Back to draft" the primary button on an issued
    // quotation, which is the same failure as the sort_order one below in a new disguise.
    moves.find((move) => move.isForward) ??
    // Only then a backward correction, because at this point there is nothing forward left.
    moves.find((move) => !move.toIsTerminal) ??
    moves[0];
  return {
    primary: forward,
    secondary: moves.filter((move) => move.transitionId !== forward.transitionId),
  };
}
