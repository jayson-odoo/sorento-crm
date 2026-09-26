/**
 * `sales_opportunity` joins the portal form kind list (UAC S2-10; plan section 16: "the kind
 * joins the Market Segments grantable list and the kind labels").
 *
 * Picked `ADDITIONAL_LANDING_KINDS` (derived from `LANDING_KINDS`, section 2's precedent for
 * `price_tag_request`) as the "grantable additional kinds" list the captain's brief named as
 * either `GRANTABLE_ADDITIONAL_KINDS` or an extension of `ADDITIONAL_LANDING_KINDS` - noted in
 * the tester's report.
 */
import { describe, expect, it } from 'vitest';
import {
  ADDITIONAL_LANDING_KINDS,
  isLandingKind,
  portalFormKindLabel,
} from './portal-form-kinds';

describe('sales_opportunity portal form kind', () => {
  it('labels sales_opportunity as "Sales Opportunities"', () => {
    expect(portalFormKindLabel('sales_opportunity')).toBe('Sales Opportunities');
  });

  it('is a recognised landing kind, not a base submission kind', () => {
    expect(isLandingKind('sales_opportunity')).toBe(true);
  });

  it('joins the Market Segments grantable-additional-kinds list', () => {
    expect(ADDITIONAL_LANDING_KINDS).toContain('sales_opportunity');
  });
});
