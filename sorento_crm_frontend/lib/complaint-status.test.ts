import { describe, it, expect } from 'vitest';

import {
  complaintStatusLabel,
  complaintStatusPillClass,
  COMPLAINT_STATUS_PILL_CLASS,
} from './complaint-status';

describe('complaint-status (UAC-D4: fulfilled pill + label)', () => {
  it('fulfilled has its own dedicated label', () => {
    expect(complaintStatusLabel('fulfilled')).toBe('Fulfilled');
  });

  it('fulfilled has its own pill colour, distinct from processed_by_cs', () => {
    const fulfilled = complaintStatusPillClass('fulfilled');
    expect(fulfilled).toBe(COMPLAINT_STATUS_PILL_CLASS.fulfilled);
    expect(fulfilled).not.toBe(complaintStatusPillClass('processed_by_cs'));
    // green != the default muted fallback
    expect(fulfilled).not.toBe(complaintStatusPillClass('something-unknown'));
  });

  it('is case-insensitive', () => {
    expect(complaintStatusLabel('FULFILLED')).toBe('Fulfilled');
    expect(complaintStatusPillClass('Fulfilled')).toBe(
      COMPLAINT_STATUS_PILL_CLASS.fulfilled,
    );
  });

  it('processed_by_cs still labels correctly (no regression)', () => {
    expect(complaintStatusLabel('processed_by_cs')).toBe('Processed by CS');
  });
});
