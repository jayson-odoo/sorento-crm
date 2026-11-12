/**
 * FILES-MOVE-DUPLICATE: the one notice a move shows. Every item that could move has
 * moved; each one that did not is named with its plain reason.
 */
export interface MoveSkipped {
  name: string;
  reason: string;
}

export interface MoveOutcome {
  moved: number;
  notMoved: MoveSkipped[];
}

function sentence(item: MoveSkipped): string {
  const reason = (item.reason || '').trim();
  if (!reason) return `${item.name} could not be moved.`;
  const text = reason.startsWith(item.name) ? reason : `${item.name}: ${reason}`;
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

export function summarizeMove({ moved, notMoved }: MoveOutcome): { ok: boolean; text: string } {
  if (notMoved.length === 0) return { ok: true, text: `${moved} moved.` };
  return {
    ok: false,
    text: `${moved} moved. ${notMoved.length} not moved: ${notMoved.map(sentence).join(' ')}`,
  };
}
