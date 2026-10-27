/**
 * FULFIL-SO-REMARK (AC-5, AC-6): the two-line decision the backend rules module
 * (`app/services/so_remark_rules.py`) makes, mirrored over the board's per-line `is_mockup`
 * flags so the Confirm guide prefills the word the purchasing email prints.
 */

export const MOCKUP_WORD = 'Mockup';

/** AC-5: the order's remark type, else `Mockup` when any chosen line is a mockup line, else blank. */
export function defaultSoRemark(
  remarkType: string | null | undefined,
  chosenFlags: readonly boolean[],
): string {
  if (remarkType) return remarkType;
  return chosenFlags.some(Boolean) ? MOCKUP_WORD : '';
}

/** AC-6: label the mockup lines only when the chosen lines mix mockup and actual lines. */
export function shouldLabelMockupLines(
  chosenFlags: readonly boolean[],
): boolean {
  return chosenFlags.some(Boolean) && !chosenFlags.every(Boolean);
}
