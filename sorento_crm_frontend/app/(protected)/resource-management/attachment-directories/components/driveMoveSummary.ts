/**
 * FILES-MOVE-DUPLICATE: the one notice a move shows. Counts what moved as is, what was
 * renamed and what replaced a file; names what the user skipped and what could not move.
 */
export interface MoveSkipped {
  name: string;
  reason: string;
}

export interface MoveOutcome {
  /** Cancel / X / Esc in the conflict window: nothing was moved. */
  cancelled: boolean;
  /** Moved under its own name, with no conflict. */
  moved: number;
  renamed: number;
  replaced: number;
  /** Files the user chose to skip. */
  skipped: string[];
  /** Files that could not move, with the plain reason. */
  notMoved: MoveSkipped[];
}

const NAMED_AT_MOST = 3;

function sentence(item: MoveSkipped, verb: string): string {
  const reason = (item.reason || '').trim();
  if (!reason) return `${item.name} could not be ${verb}.`;
  const text = reason.startsWith(item.name) ? reason : `${item.name}: ${reason}`;
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

export function summarizeMove(
  outcome: MoveOutcome,
  verb: 'moved' | 'restored' = 'moved'
): { ok: boolean; text: string } {
  if (outcome.cancelled) {
    const action = verb === 'restored' ? 'Restore' : 'Move';
    return { ok: true, text: `${action} cancelled. Nothing was ${verb}.` };
  }
  const counts = [`${outcome.moved} ${verb}`];
  if (outcome.renamed) counts.push(`${outcome.renamed} renamed`);
  if (outcome.replaced) counts.push(`${outcome.replaced} replaced`);
  let text = `${counts.join(', ')}.`;

  const { skipped, notMoved } = outcome;
  if (skipped.length) {
    const shown = skipped.slice(0, NAMED_AT_MOST).join(', ');
    const more = skipped.length > NAMED_AT_MOST ? ` and ${skipped.length - NAMED_AT_MOST} more` : '';
    text += ` ${skipped.length} skipped: ${shown}${more}.`;
  }
  if (notMoved.length) {
    const shown = notMoved.slice(0, NAMED_AT_MOST).map((item) => sentence(item, verb)).join(' ');
    const more =
      notMoved.length > NAMED_AT_MOST ? ` And ${notMoved.length - NAMED_AT_MOST} more.` : '';
    text += ` ${notMoved.length} not ${verb}: ${shown}${more}`;
  }
  return { ok: notMoved.length === 0, text };
}
