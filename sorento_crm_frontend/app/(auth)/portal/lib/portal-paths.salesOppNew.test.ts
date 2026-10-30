/** PORTAL-P4-REQUESTS review fix (red): create is a modal on the opportunities list, so there is no /new page. */
import { describe, expect, it } from 'vitest';
import { crmPathForPortalPath } from './portal-paths';

describe('crmPathForPortalPath sales_opportunity/new', () => {
  it('maps to the list, not a /new page', () => {
    expect(crmPathForPortalPath('/portal/c/SLUG123456/sales_opportunity/new')).toBe('/sales/opportunities');
  });
  it('other kinds keep their /new page', () => {
    expect(crmPathForPortalPath('/portal/c/SLUG123456/complaint/new')).toBe('/complaint-management/complaints/new');
  });
});
