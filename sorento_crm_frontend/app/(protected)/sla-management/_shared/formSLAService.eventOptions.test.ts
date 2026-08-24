import { describe, it, expect } from 'vitest';
import { FORM_SLA_EVENT_OPTIONS } from './formSLAService';

// Regression: the `voided` form event must be selectable as a Respond/Resolve
// event in Form SLA config for every form type that has a Void action, so an
// admin can wire void to stop (respond/resolve) the SLA tracker.
describe('FORM_SLA_EVENT_OPTIONS - voided event availability', () => {
  const VOIDABLE = [
    'purchase_request',
    'sponsorship_form',
    'complaint',
    'stock_inquiry',
  ] as const;

  it.each(VOIDABLE)('exposes "voided" for %s', (kind) => {
    expect(FORM_SLA_EVENT_OPTIONS[kind]).toContain('voided');
  });

  it('does not expose "voided" for ticket (no Void action)', () => {
    expect(FORM_SLA_EVENT_OPTIONS.ticket).not.toContain('voided');
  });

  it('keeps voided as the last option (appended, order preserved)', () => {
    for (const kind of VOIDABLE) {
      const opts = FORM_SLA_EVENT_OPTIONS[kind];
      expect(opts[opts.length - 1]).toBe('voided');
      // no accidental duplication
      expect(opts.filter((e) => e === 'voided')).toHaveLength(1);
    }
  });
});
