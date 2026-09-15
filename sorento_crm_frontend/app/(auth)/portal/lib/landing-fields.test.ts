/**
 * Review round 2 (r8): `applyLandingFilters`'s date-range bound compares a
 * ROW timestamp parsed as LOCAL time (a naive ISO string with no timezone
 * designator, e.g. `created_at`) against a `from`/`to` BOUND parsed as UTC
 * (a bare `YYYY-MM-DD`, per the ECMA-262 Date-parsing spec) - the two
 * `new Date(...)` calls disagree on what "midnight" means, so a row created
 * just after local midnight on the `from` day is compared against a UTC
 * boundary that is hours ahead of it and gets excluded.
 */
import { describe, it, expect } from 'vitest';
import { applyLandingFilters, landingFieldsFor, submissionStatusLabel } from './landing-fields';
import type { PortalSubmissionSummary } from './portal-client';

const FIELDS = landingFieldsFor('stock_inquiry');

function row(created_at: string): PortalSubmissionSummary {
  return {
    id: 'row-1',
    kind: 'stock_inquiry',
    title: 'ZZT Row',
    document_number: 'SI-0001',
    reference: null,
    status: 'new',
    is_editable: true,
    is_draft: false,
    created_at,
  } as PortalSubmissionSummary;
}

describe('applyLandingFilters - Created date range (review round 2)', () => {
  it('a "from 2026-09-12" filter includes a naive-local row created just after local midnight that day', () => {
    const rows = [row('2026-09-12T01:00:00')];

    const result = applyLandingFilters(rows, FIELDS, {
      created_at: { from: '2026-09-12' },
    });

    expect(result).toHaveLength(1);
  });
});

describe('submissionStatusLabel for a price tag request (r9 review-round leftover R7)', () => {
  /**
   * `submissionStatusLabel` falls through to `statusLabel`, which reads its
   * own `SUBMISSION_STATUS_LABELS` map in `portal-client.ts` - a SEPARATE map
   * from `lib/price-tag-status.ts` that the CRM side already uses. That map
   * still carries the retired `ready` status and never gained the two
   * collection statuses, so a price tag card on the portal landing/list
   * printed the raw status code for both instead of a title-cased label.
   */
  function priceTagRow(status: string): PortalSubmissionSummary {
    return {
      id: 'row-1',
      kind: 'price_tag_request',
      title: 'ZZT Price Tag Row',
      document_number: 'PT-202609-0001',
      reference: null,
      status,
      is_editable: true,
      is_draft: false,
      created_at: '2026-09-14T00:00:00Z',
    } as PortalSubmissionSummary;
  }

  it('titlecases "ready_for_collection" rather than printing the raw code', () => {
    expect(submissionStatusLabel(priceTagRow('ready_for_collection'))).toBe(
      'Ready for collection',
    );
  });

  it('titlecases "collected" rather than printing the raw code', () => {
    expect(submissionStatusLabel(priceTagRow('collected'))).toBe('Collected');
  });
});
