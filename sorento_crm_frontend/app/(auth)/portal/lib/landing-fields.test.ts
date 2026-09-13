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
import { applyLandingFilters, landingFieldsFor } from './landing-fields';
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
