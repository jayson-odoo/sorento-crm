/**
 * Number wording shared by the report pivot and its chart. A plain module, not a component
 * file: a 'use client' component that also exports a helper loses Fast Refresh
 * (LESSONS-LEARNT 106).
 */

const WHOLE = new Intl.NumberFormat('en-MY', { maximumFractionDigits: 0 });

/**
 * Whole ringgit, the way a sales report reads on screen (the exported workbook keeps the
 * sen), and a negative in brackets, as the client's own variance row prints it: (1,234),
 * never -1,234.
 */
export function wholeRinggit(value: string | number): string {
  const amount = Math.round(Number(value));
  if (!Number.isFinite(amount)) return String(value);
  const text = WHOLE.format(Math.abs(amount));
  return amount < 0 ? `(${text})` : text;
}
