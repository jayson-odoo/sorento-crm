import { describe, expect, it } from 'vitest';
import { auditFieldChanges, formatAuditValue } from './audit-fields';

describe('audit values: dates read in the app format, stamps in Malaysia time', () => {
  it('formats a stored date as DD/MM/YYYY', () => {
    expect(formatAuditValue('2026-12-09')).toBe('09/12/2026');
  });

  it('formats a naive UTC stamp in Malaysia time (+8)', () => {
    // 14:22 UTC is 10:22 pm in Kuala Lumpur.
    expect(formatAuditValue('2026-11-02T14:22:23.073162')).toMatch(/^02\/11\/2026, 10:22\s?pm$/i);
  });

  it('leaves other text alone', () => {
    expect(formatAuditValue('Stock from KL')).toBe('Stock from KL');
    expect(formatAuditValue('CG-202611-010')).toBe('CG-202611-010');
  });

  it('reads a sample request date answer change with values', () => {
    const lines = auditFieldChanges(
      { proposed_delivery_date: null, date_answered_at: null },
      { proposed_delivery_date: '2026-12-09', date_answered_at: '2026-11-02T14:22:23' },
    );
    expect(lines.map((l) => (l.kind === 'line' ? l.text : l.label))).toEqual([
      'Proposed delivery date: (empty) → 09/12/2026',
      expect.stringMatching(/^Date answered at: \(empty\) → 02\/11\/2026, 10:22\s?pm$/i),
    ]);
  });
});
