/**
 * AC-QTSO-CRM: the fixed sentences. The answer wording (done, refused, pending, stale) is the
 * server's, pinned by tests/test_project_autocount_*.py.
 */
import { describe, expect, it } from 'vitest';
import {
  AUTOCOUNT_NOT_ACCEPTED_TEXT,
  AUTOCOUNT_NOT_IN_AUTOCOUNT_TEXT,
  AUTOCOUNT_PENDING_TEXT,
  AUTOCOUNT_SWITCHED_OFF_HERE,
  AUTOCOUNT_UNREACHABLE_TEXT,
  AUTOCOUNT_WAITING_TEXT,
} from './autocountWriteWording';

describe('autocount write wording', () => {
  it('holds the plan sentences', () => {
    expect(AUTOCOUNT_WAITING_TEXT).toBe('Waiting for AutoCount');
    expect(AUTOCOUNT_SWITCHED_OFF_HERE).toBe('Changes to AutoCount are switched off here');
    expect(AUTOCOUNT_UNREACHABLE_TEXT).toBe('Could not reach AutoCount');
    expect(AUTOCOUNT_PENDING_TEXT).toBe(
      'Sent; AutoCount has not confirmed yet. It will show after the next sync.',
    );
    expect(AUTOCOUNT_NOT_ACCEPTED_TEXT).toBe('The customer has not accepted this quotation yet');
    expect(AUTOCOUNT_NOT_IN_AUTOCOUNT_TEXT).toBe('Not in AutoCount yet');
  });
});
