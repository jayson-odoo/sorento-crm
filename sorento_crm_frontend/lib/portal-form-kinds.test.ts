/**
 * Reviewer should-fix 9: `isLandingKind` answers for the generic `[type]` submission-tab
 * machinery (tab list, EMPTY_LISTS, the shared submissions fetch) - `sales_opportunity` has
 * none of that, its own bespoke pages instead, so it must never match here even though it is
 * still grantable and labelled like any other kind.
 */
import { describe, expect, it } from 'vitest';
import {
  ADDITIONAL_LANDING_KINDS,
  LANDING_KINDS,
  SALES_OPPORTUNITY_KIND,
  isLandingKind,
  portalFormKindLabel,
} from './portal-form-kinds';

describe('isLandingKind', () => {
  it('fix reviewer-9: does not match sales_opportunity', () => {
    expect(isLandingKind(SALES_OPPORTUNITY_KIND)).toBe(false);
  });

  it('still matches every real LANDING_KINDS entry', () => {
    for (const kind of LANDING_KINDS) {
      expect(isLandingKind(kind)).toBe(true);
    }
  });
});

describe('sales_opportunity stays grantable and labelled despite the isLandingKind fix', () => {
  it('is in the Market Segments admin grantable list', () => {
    expect(ADDITIONAL_LANDING_KINDS).toContain(SALES_OPPORTUNITY_KIND);
  });

  it('has a real label, not the raw code', () => {
    expect(portalFormKindLabel(SALES_OPPORTUNITY_KIND)).toBe('Sales Opportunities');
  });
});
