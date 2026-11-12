/**
 * QUOTE-DUPLICATE-PARTY crew pass: a system event never shows its internal key. The writer's own
 * sentence (body_text) wins; otherwise the known wording; otherwise the key made readable.
 */
import { describe, expect, it } from 'vitest';
import { formatSystemEvent } from './formatSystemEvent';

describe('formatSystemEvent', () => {
  it('shows the sentence the writer saved', () => {
    expect(
      formatSystemEvent('quotation_created', { document_no: 'PRJQ-2026-0009' }, 'PRJQ-2026-0009 copied from PRJQ-2026-0003 for ARKITEK CONTOH'),
    ).toBe('PRJQ-2026-0009 copied from PRJQ-2026-0003 for ARKITEK CONTOH');
    expect(
      formatSystemEvent('quotation_approval_carried', {}, 'Test Person carried the approval of PRJQ-2026-0003 to PRJQ-2026-0009'),
    ).toBe('Test Person carried the approval of PRJQ-2026-0003 to PRJQ-2026-0009');
  });

  it('keeps the known wording for ticket events', () => {
    expect(formatSystemEvent('entity.created', { ticket_number: 'T-1' })).toBe('Ticket T-1 was created.');
    expect(formatSystemEvent('assignee.changed', {}, 'ignored')).toBe('Assignee changed.');
  });

  it('never shows a raw key', () => {
    expect(formatSystemEvent('quotation_created', {})).toBe('Quotation created');
    expect(formatSystemEvent('stage_changed', null)).toBe('Stage changed');
    expect(formatSystemEvent(null, null)).toBe('System event');
  });
});
