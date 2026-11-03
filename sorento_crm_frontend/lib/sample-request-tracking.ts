/**
 * PS-SAMPLE-TRACKING Stage 1: what the sample team said about the requested delivery date, as
 * the salesperson reads it, and the check the Start processing dialog runs before it sends.
 * Plan: documentation/plans/project-sales/PLAN-sample-tracking-02nov.md (rules 2-3).
 */
import type { SampleRequestDateAnswer } from '@/types/sampleRequest';

export const STAGE_LABELS = { processing: 'Processing', delivery: 'Delivery' } as const;

/** The date the list shows and sorts by: the team's proposed date when it gave one. */
export function shownDeliveryDate(
  row: SampleRequestDateAnswer & { delivery_date: string | null },
): { date: string | null; isNew: boolean } {
  if (row.date_feasible === false && row.proposed_delivery_date) {
    return { date: row.proposed_delivery_date, isNew: true };
  }
  return { date: row.delivery_date, isNew: false };
}

/** "Can meet the requested date" / "Proposes 19 Nov 2026"; null before the team answers. */
export function dateAnswerText(
  answer: SampleRequestDateAnswer,
  formatDate: (iso: string) => string,
): string | null {
  if (answer.date_feasible === true) return 'Can meet the requested date';
  if (answer.date_feasible === false && answer.proposed_delivery_date) {
    return `Proposes ${formatDate(answer.proposed_delivery_date)}`;
  }
  return null;
}

/** The first problem with a date answer, or null when it can be sent. `today` is YYYY-MM-DD. */
export function dateAnswerProblem(
  feasible: boolean | null,
  proposed: string,
  today: string,
): string | null {
  if (feasible === null) return 'Say whether the requested date can be met.';
  if (feasible) return null;
  if (!proposed) return 'Enter the date the sample team can deliver.';
  if (proposed < today) return 'The proposed date cannot be in the past.';
  return null;
}
