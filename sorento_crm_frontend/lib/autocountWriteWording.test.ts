/**
 * AC-QTSO-CRM Phase 2 (red): the plain wording of every AutoCount write answer.
 *
 * Plan "Results and refusals" (same wording table as #2168) and "Phase 2 contract / Capability
 * shape". One module owns the words so the dialog, the greyed menu items and the toasts cannot
 * drift. Export names are this test's proposal; the strings are the plan's.
 */
import { describe, expect, it } from 'vitest';
import {
  AUTOCOUNT_NOT_ACCEPTED_TEXT,
  AUTOCOUNT_PENDING_TEXT,
  AUTOCOUNT_SWITCHED_OFF_HERE,
  AUTOCOUNT_UNREACHABLE_TEXT,
  AUTOCOUNT_WAITING_TEXT,
  reasonCodeText,
  staleText,
  writeOutcomeText,
} from './autocountWriteWording';

describe('writeOutcomeText', () => {
  it('done names the document that now exists', () => {
    expect(writeOutcomeText('done', { docNo: 'SO412345' })).toBe('SO412345 created in AutoCount');
  });

  it('refused quotes the reason and says nothing was changed', () => {
    expect(writeOutcomeText('refused', { reason: 'Item code ZZT-X is not in AutoCount' })).toBe(
      'AutoCount refused: Item code ZZT-X is not in AutoCount. Nothing was changed.',
    );
  });

  it('a 202 says AutoCount has not confirmed yet', () => {
    expect(writeOutcomeText('pending_verification')).toBe(
      'Sent; AutoCount has not confirmed yet. It will show after the next sync.',
    );
    expect(AUTOCOUNT_PENDING_TEXT).toBe(writeOutcomeText('pending_verification'));
  });

  it('an unreachable gateway says so', () => {
    expect(writeOutcomeText('unreachable')).toBe('Could not reach AutoCount');
    expect(AUTOCOUNT_UNREACHABLE_TEXT).toBe('Could not reach AutoCount');
  });
});

describe('reasonCodeText', () => {
  it('VENDOR_UNSUPPORTED and anything unknown read as Waiting for AutoCount', () => {
    expect(reasonCodeText('VENDOR_UNSUPPORTED')).toBe('Waiting for AutoCount');
    expect(reasonCodeText('SOMETHING_NEW')).toBe('Waiting for AutoCount');
    expect(reasonCodeText(null)).toBe('Waiting for AutoCount');
    expect(AUTOCOUNT_WAITING_TEXT).toBe('Waiting for AutoCount');
  });

  it.each(['WRITE_DISABLED', 'WRITE_NOT_ALLOWED', 'WRITE_COMPANY_NOT_TEST'])(
    '%s reads as switched off here',
    (code) => {
      expect(reasonCodeText(code)).toBe('Changes to AutoCount are switched off here');
      expect(AUTOCOUNT_SWITCHED_OFF_HERE).toBe('Changes to AutoCount are switched off here');
    },
  );
});

describe('staleText', () => {
  it('names the stored date as dd/mm/yyyy and sends the reader to Compare', () => {
    expect(staleText('2026-10-01T09:30:00')).toBe(
      'Changed in AutoCount since 01/10/2026, open Compare first.',
    );
  });
});

describe('quotation acceptance', () => {
  it('a quotation the customer has not accepted is greyed with this sentence', () => {
    expect(AUTOCOUNT_NOT_ACCEPTED_TEXT).toBe('The customer has not accepted this quotation yet');
  });
});
