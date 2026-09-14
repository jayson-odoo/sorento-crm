import type { UnpostableLine, UnpostableReason } from './fulfilmentBoard';

/** How many names a sentence carries before it stops being a sentence and becomes a wall. */
const NAMED_CAP = 5;

/**
 * The sentences naming what this confirmation leaves out for one reason, and the fix.
 *
 * Every line reaching here carries a SAVED decision or is covered-and-decided (8 Sep 2026
 * ruling, reverses R11: an untouched, uncovered line is never posted, so it never lands here
 * unpostable at all) - so every one of them is a line the planner composed, and NAMED, capped
 * at five names, since a list longer than that is scrolled past rather than read.
 *
 * ITS OWN MODULE, beside the types it speaks about. It used to be exported from
 * `FulfilmentBoardPanel.tsx`, and a `'use client'` component file that exports a value which
 * is not a component drops out of React Fast Refresh - Next then does a FULL PAGE RELOAD for
 * any edit to it, in its own words:
 *
 *   "Fast Refresh will perform a full reload when you edit a file that's imported by modules
 *    outside of the React rendering tree. You might have a file which exports a React
 *    component but also exports a value that is imported by a non-React component file.
 *    Consider migrating the non-React component export to a separate file and importing it
 *    into both files."
 *
 * Measured on the sales-order screen the same day (13 September 2026): a reload like that
 * wipes an OPEN session - the board would come back with every decision panel closed and the
 * draft gone, and the click that followed would land on a tree that no longer had it.
 */
export function unpostableNotices(
  reason: UnpostableReason,
  lines: UnpostableLine[],
): string[] {
  if (lines.length === 0) return [];
  const names = lines
    .slice(0, NAMED_CAP)
    .map((entry) => `${entry.contribution.item_code} line ${entry.contribution.line_no}`)
    .join(', ');
  const rest = lines.length - Math.min(lines.length, NAMED_CAP);
  const named = rest > 0 ? `${names} and ${rest} more` : names;
  const one = lines.length === 1;
  const them = one ? 'it' : 'them';
  if (reason === 'no_mirror') {
    return [
      `${named} ${one ? 'is' : 'are'} not on the planning record yet, so this confirmation leaves ${them} out. Re-sync the sales order to add ${them}.`,
    ];
  }
  if (reason === 'no_reserve_warehouse') {
    return [
      `${named} ${one ? 'reserves' : 'reserve'} at a warehouse the board cannot address, so this confirmation leaves ${them} out. Amend ${them} to place the Reserve.`,
    ];
  }
  return [
    `${named} ${one ? 'buys' : 'buy'} a discontinued product with no reason given, so this confirmation leaves ${them} out. Amend ${them} to give one.`,
  ];
}
