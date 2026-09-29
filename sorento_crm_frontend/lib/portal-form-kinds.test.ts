/**
 * Fix lane round 2, F1 (owner ruling 27 Sep, PR #1296): Sales Opportunity is one kind in the
 * portal's kind selector exactly like Price Tag Request, so it IS a landing kind now. This
 * reverses reviewer should-fix 9, which kept it out while it had a bespoke landing card.
 */
import { describe, expect, it } from 'vitest';
import {
  ADDITIONAL_LANDING_KINDS,
  LANDING_KINDS,
  LANDING_LABELS,
  SALES_OPPORTUNITY_KIND,
  isLandingKind,
  isSubmissionKind,
  portalFormKindLabel,
} from './portal-form-kinds';

describe('isLandingKind', () => {
  it('matches sales_opportunity, a kind in the selector like price_tag_request', () => {
    expect(isLandingKind(SALES_OPPORTUNITY_KIND)).toBe(true);
    expect(isSubmissionKind(SALES_OPPORTUNITY_KIND)).toBe(false);
  });

  it('lists it after Price Tag Request', () => {
    expect(LANDING_KINDS.slice(-2)).toEqual(['price_tag_request', 'sales_opportunity']);
  });

  it('still matches every real LANDING_KINDS entry', () => {
    for (const kind of LANDING_KINDS) {
      expect(isLandingKind(kind)).toBe(true);
    }
  });
});

describe('sales_opportunity stays grantable and labelled', () => {
  it('is in the Market Segments admin grantable list', () => {
    expect(ADDITIONAL_LANDING_KINDS).toContain(SALES_OPPORTUNITY_KIND);
  });

  it('has a real label, singular like every other kind, not the raw code', () => {
    expect(LANDING_LABELS.sales_opportunity).toBe('Sales Opportunity');
    expect(portalFormKindLabel(SALES_OPPORTUNITY_KIND)).toBe('Sales Opportunity');
  });
});
