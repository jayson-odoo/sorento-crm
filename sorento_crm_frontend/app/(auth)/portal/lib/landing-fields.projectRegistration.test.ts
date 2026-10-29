/**
 * PROJECT-REG-PORTAL round 2 (browser pass D2, D3): a rejected registration reads Rejected
 * although the backend keeps it editable (is_draft true), and an approved one shows its PPF.
 */
import { describe, expect, it } from 'vitest';
import {
  isShownAsDraft,
  landingFieldValue,
  landingFieldsFor,
  submissionStatusLabel,
} from './landing-fields';
import type { PortalSubmissionSummary } from './portal-client';

function row(over: Record<string, unknown>): PortalSubmissionSummary {
  return {
    id: 'r1',
    kind: 'project_registration',
    title: 'TOWER',
    reference: null,
    status: 'draft',
    is_editable: true,
    is_draft: true,
    created_at: '2026-10-01T00:00:00',
    ...over,
  } as unknown as PortalSubmissionSummary;
}

describe('a rejected registration is not shown as a draft', () => {
  it('reads Rejected although it is still editable', () => {
    const rejected = row({ status: 'rejected' });
    expect(isShownAsDraft(rejected)).toBe(false);
    expect(submissionStatusLabel(rejected)).toBe('Rejected');
  });

  it('a real draft still reads Draft', () => {
    const draft = row({ status: 'draft' });
    expect(isShownAsDraft(draft)).toBe(true);
    expect(submissionStatusLabel(draft)).toBe('Draft');
  });
});

describe('an approved registration shows its PPF number', () => {
  it('the landing fields carry ppf_no and read the value', () => {
    const field = landingFieldsFor('project_registration').find((f) => f.key === 'ppf_no');
    expect(field).toBeDefined();
    expect(landingFieldValue(row({ status: 'approved', is_draft: false, ppf_no: 'PPF2610005' }), field!)).toBe(
      'PPF2610005',
    );
    expect(landingFieldValue(row({ status: 'pending', is_draft: false, ppf_no: null }), field!)).toBeNull();
  });
});
