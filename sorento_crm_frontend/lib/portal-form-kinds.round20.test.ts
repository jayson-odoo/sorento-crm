/**
 * OCN-ORDER-CHANGE-NOTICE round 20 (I1, I2, I4): `order_change_notice` is ONE opt-in portal form
 * kind, registered once in the shared lists the screens read (no screen keeps its own).
 */
import { describe, expect, it } from 'vitest';
import {
  ADDITIONAL_LANDING_KINDS,
  LANDING_KINDS,
  LANDING_LABELS,
  isLandingKind,
  orderLandingKinds,
  portalFormKindLabel,
} from './portal-form-kinds';
import { MY_REQUEST_STAFF_PAGES, myRequestStaffPath } from './my-requests-staff-pages';

describe('order_change_notice portal form kind (I1)', () => {
  it('is a landing kind', () => {
    expect(isLandingKind('order_change_notice')).toBe(true);
    expect(LANDING_KINDS).toContain('order_change_notice');
  });

  it('is labelled "Order Change Notice"', () => {
    expect(portalFormKindLabel('order_change_notice')).toBe('Order Change Notice');
    expect(LANDING_LABELS['order_change_notice' as keyof typeof LANDING_LABELS]).toBe(
      'Order Change Notice',
    );
  });

  it('joins the grantable additional kinds (opt-in, I2): the market segment editor offers it', () => {
    expect(ADDITIONAL_LANDING_KINDS).toContain('order_change_notice');
  });

  it('is kept by the landing order helper', () => {
    expect(orderLandingKinds(['complaint', 'order_change_notice'])).toContain('order_change_notice');
  });
});

describe('order_change_notice MY REQUESTS staff page (I4)', () => {
  it('points at the OCN list with the view_own and create slugs', () => {
    expect(MY_REQUEST_STAFF_PAGES['order_change_notice']).toEqual({
      path: '/procurement-management/order-change-notices',
      permission: 'procurement.order_change_notices.view_own',
      create: 'procurement.order_change_notices.create',
    });
    expect(myRequestStaffPath('order_change_notice')).toBe(
      '/procurement-management/order-change-notices',
    );
  });
});
