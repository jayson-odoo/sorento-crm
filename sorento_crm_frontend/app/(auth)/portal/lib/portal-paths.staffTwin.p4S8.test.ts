/**
 * PORTAL-P4-REQUESTS S8: the CRM twin of a portal path is the STAFF page, never /my-requests.
 */
import { describe, expect, it } from 'vitest';
import * as paths from './portal-paths';

const crm = (p: string) =>
  (paths as unknown as { crmPathForPortalPath: (x: string) => string | null }).crmPathForPortalPath(p);

const S = 'SLUG123456';
describe('crmPathForPortalPath -> staff pages', () => {
  it.each([
    [`/portal/c/${S}`, '/procurement-management/stock-inquiries'],
    [`/portal/c/${S}?type=complaint`, '/complaint-management/complaints'],
    [`/portal/c/${S}?token=T1&type=sales_opportunity`, '/sales/opportunities'],
    [`/portal/c/${S}?token=T1`, '/procurement-management/stock-inquiries'],
    [`/portal/c/${S}/complaint/abc-123`, '/complaint-management/complaints/abc-123'],
    [`/portal/c/${S}/complaint/new`, '/complaint-management/complaints/new'],
    [`/portal/c/${S}/sample_request/new`, '/project-sales/sample-requests/new'],
    [`/portal/c/${S}/sample_request/r1`, '/project-sales/sample-requests/r1'],
    [`/portal/c/${S}/new_product_application/n1`, '/procurement-management/new-product-applications/n1'],
    [`/portal/c/${S}/price_tag_request/p1`, '/dealer-kit/price-tag-requests/p1'],
    [`/portal/c/${S}/purchase_request/q1`, '/procurement-management/purchase-requests/q1'],
    [`/portal/c/${S}/sponsorship_form/s1`, '/procurement-management/sponsorship-forms/s1'],
    [`/portal/c/${S}/stock_inquiry/i1`, '/procurement-management/stock-inquiries/i1'],
    [`/portal/c/${S}/sales_opportunity/o1`, '/sales/opportunities/o1'],
  ])('%s -> %s', (from, to) => {
    expect(crm(from)).toBe(to);
  });

  it('never returns a /my-requests path and never carries the token', () => {
    const out = crm(`/portal/c/${S}/complaint/abc?token=SECRET&revise=1`) as string;
    expect(out.startsWith('/complaint-management/complaints/abc')).toBe(true);
    expect(out).not.toContain('/my-requests');
    expect(out).not.toContain('token');
    expect(out).not.toContain('SECRET');
  });

  it.each([
    [`/portal/c/${S}/verify`],
    [`/portal?token=T1`],
    ['/portal'],
    ['/my-requests'],
    ['/'],
  ])('%s -> null', (from) => {
    expect(crm(from)).toBeNull();
  });
});
