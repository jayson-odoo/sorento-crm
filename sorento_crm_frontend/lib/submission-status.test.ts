import { describe, it, expect } from 'vitest';

import { isAwaitingReview, RESUBMITTED } from './submission-status';

describe('submission-status (RESUBMITTED-STATUS)', () => {
  it('treats resubmitted like the stage it stands in for', () => {
    expect(isAwaitingReview('submitted')).toBe(true);
    expect(isAwaitingReview(RESUBMITTED)).toBe(true);
    expect(isAwaitingReview('Resubmitted ')).toBe(true);
    expect(isAwaitingReview('approved')).toBe(false);
    expect(isAwaitingReview(null)).toBe(false);
  });

  it('takes the stage for stage-based forms', () => {
    expect(isAwaitingReview('pending_project_sales', 'pending_project_sales')).toBe(true);
    expect(isAwaitingReview('resubmitted', 'pending_project_sales')).toBe(true);
    expect(isAwaitingReview('submitted', 'pending_project_sales')).toBe(false);
  });
});
