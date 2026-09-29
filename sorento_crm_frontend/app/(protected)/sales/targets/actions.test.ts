/**
 * `deleteSubject` (S1-28, plan 3.8): the parked delete's countdown names the child count, so
 * "Deleting North FY26 H2 and 2 agent targets" reads as a warning, not a guess. Round 2 review:
 * expected GREEN already (`actions.tsx` already implements this), kept as a regression guard -
 * mutating `deleteSubject` to return only the name must turn this red.
 */
import { describe, expect, it } from 'vitest';
import { deleteSubject } from './actions';

describe('deleteSubject', () => {
  it('is the name alone with no children', () => {
    expect(deleteSubject({ id: 't1', name: 'North FY26 H2', child_count: 0 })).toBe('North FY26 H2');
  });

  it('names one child in the singular', () => {
    expect(deleteSubject({ id: 't1', name: 'North FY26 H2', child_count: 1 })).toBe(
      'North FY26 H2 and 1 agent target',
    );
  });

  it('names two or more children in the plural, matching the plan wording exactly', () => {
    expect(deleteSubject({ id: 't1', name: 'North FY26 H2', child_count: 2 })).toBe(
      'North FY26 H2 and 2 agent targets',
    );
  });
});
