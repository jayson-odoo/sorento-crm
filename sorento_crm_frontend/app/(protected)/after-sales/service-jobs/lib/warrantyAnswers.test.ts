/**
 * AFTER-SALES-P2 red tests (UAC F1, F2): answer wording shared by the job page and the jobs list.
 *
 * Module the coder builds: `./warrantyAnswers` (this folder) exporting
 *   answerLabel(verdict: string): string        covered|expired|defect_not_covered|no_term|unknown
 *   summaryLabel(summary: string | null): string  covered|partly_covered|not_covered|unknown|null
 */
import { describe, it, expect } from 'vitest';
import { answerLabel, summaryLabel } from './warrantyAnswers';

describe('warranty answer wording', () => {
  it('names the five per-term answers', () => {
    expect(answerLabel('covered')).toBe('Covered');
    expect(answerLabel('expired')).toBe('Expired');
    expect(answerLabel('defect_not_covered')).toBe('Defect not covered');
    expect(answerLabel('no_term')).toBe('No term');
    expect(answerLabel('unknown')).toBe('Unknown');
  });

  it('names the four job summaries and shows a dash when the job has no products', () => {
    expect(summaryLabel('covered')).toBe('Covered');
    expect(summaryLabel('partly_covered')).toBe('Partly covered');
    expect(summaryLabel('not_covered')).toBe('Not covered');
    expect(summaryLabel('unknown')).toBe('Unknown');
    expect(summaryLabel(null)).toBe('-');
  });

  it('never leaks a raw snake_case code for an unexpected value', () => {
    expect(answerLabel('something_new')).not.toMatch(/_/);
  });
});
