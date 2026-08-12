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

describe('complaint-status (skip stage: settled_on_site pill + label)', () => {
  it('reads as a sentence, not a snake_case code', () => {
    // Title-casing would give "Settled On Site" - the explicit map exists for this.
    expect(complaintStatusLabel('settled_on_site')).toBe('Settled on site');
  });

  it('is visually distinct from the DO-delivered terminal state', () => {
    // Both are terminal and both are "done and good", but they mean different things:
    // fulfilled = a replacement was delivered; settled_on_site = the technician fixed
    // it and no replacement ever existed. A shared colour would hide that.
    const settled = complaintStatusPillClass('settled_on_site');
    expect(settled).toBe(COMPLAINT_STATUS_PILL_CLASS.settled_on_site);
    expect(settled).not.toBe(complaintStatusPillClass('fulfilled'));
    expect(settled).not.toBe(complaintStatusPillClass('processed_by_cs'));
    expect(settled).not.toBe(complaintStatusPillClass('something-unknown'));
  });

  it('is case-insensitive like every other status', () => {
    expect(complaintStatusLabel('SETTLED_ON_SITE')).toBe('Settled on site');
    expect(complaintStatusPillClass('Settled_On_Site')).toBe(
      COMPLAINT_STATUS_PILL_CLASS.settled_on_site,
    );
  });
});
