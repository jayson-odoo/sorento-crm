import { describe, expect, it } from 'vitest';
import { customerTriggerLabel as portalLabel } from './customerOrProspect';
import { customerTriggerLabel as crmLabel } from '@/app/(protected)/sales/opportunities/lib/customerOrProspect';

// Browser pass of fix round 2: a picked prospect showed its option text ("Add "X" as a new
// prospect") in the closed field instead of the name.
describe.each([
  ['portal', portalLabel],
  ['crm', crmLabel],
])('customerTriggerLabel (%s)', (_, label) => {
  it('shows only the name for a picked prospect', () => {
    expect(label({ value: 'prospect:Fresh Prospect', label: 'Add "Fresh Prospect" as a new prospect' })).toBe(
      'Fresh Prospect',
    );
  });
  it('keeps a customer label as is', () => {
    expect(label({ value: 'c-1', label: 'C001 - Lim Tiles' })).toBe('C001 - Lim Tiles');
  });
});
