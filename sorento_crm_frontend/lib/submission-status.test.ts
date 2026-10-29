import { describe, it, expect } from 'vitest';

import {
  APPEAL_VERB,
  APPEALED_LABEL,
  appealWording,
  isAwaitingReview,
  RESUBMITTED,
  submitVerb,
} from './submission-status';
import { formatStatusLabel } from './status-badge';
import { statusLabel as portalStatusLabel } from '@/app/(auth)/portal/lib/portal-client';
import { STOCK_INQUIRY_STATUS_LABELS } from '@/app/(protected)/procurement-management/stock-inquiries/types/stockInquiry.types';

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

// Owner, 28 Oct: every form calls a send-back after a rejection an appeal. The stored value
// stays `resubmitted`; only what a person reads changes.
describe('appeal wording (COMPLAINT-APPEAL-WORDING, every form)', () => {
  it('the send button of a rejected form reads Appeal', () => {
    expect(submitVerb('rejected')).toBe('Appeal');
    expect(submitVerb('draft')).toBe('Submit');
    expect(APPEAL_VERB).toBe('Appeal');
    expect(APPEALED_LABEL).toBe('Appealed');
  });

  it('every shared label map reads resubmitted as Appealed', () => {
    expect(formatStatusLabel('resubmitted')).toBe('Appealed');
    expect(formatStatusLabel('pending_approval')).toBe('Pending Approval');
    expect(portalStatusLabel('resubmitted')).toBe('Appealed');
    expect(STOCK_INQUIRY_STATUS_LABELS.resubmitted).toBe('Appealed');
  });

  it('rewords a status line, case kept', () => {
    expect(appealWording('status: rejected → resubmitted')).toBe('status: rejected → appealed');
    expect(appealWording('Status: Rejected → Resubmitted')).toBe('Status: Rejected → Appealed');
  });
});
