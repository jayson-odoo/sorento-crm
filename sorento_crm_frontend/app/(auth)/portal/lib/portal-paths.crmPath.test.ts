/**
 * PORTAL-P3-ROLE-MENU round 2, B1: the CRM twin of a portal path, for deep links.
 */
import { describe, expect, it } from 'vitest';

import * as paths from './portal-paths';

const crm = (p: string) =>
  (paths as unknown as { crmPathForPortalPath: (x: string) => string | null }).crmPathForPortalPath(p);

describe('crmPathForPortalPath', () => {
  it.each([
    ['/portal/c/SLUG123456', '/my-requests'],
    ['/portal/c/SLUG123456?type=complaint', '/my-requests?type=complaint'],
    ['/portal/c/SLUG123456?token=T1&type=stock_inquiry', '/my-requests?type=stock_inquiry'],
    ['/portal/c/SLUG123456?token=T1', '/my-requests'],
    ['/portal/c/SLUG123456/complaint/abc-123', '/my-requests/complaint/abc-123'],
    ['/portal/c/SLUG123456/complaint/new', '/my-requests/complaint/new'],
    ['/portal/c/SLUG123456/sample_request/new', '/my-requests/sample_request/new'],
  ])('%s -> %s', (from, to) => {
    expect(crm(from)).toBe(to);
  });

  it('keeps other query params and always drops the token', () => {
    const out = crm('/portal/c/SLUG123456/complaint/abc?token=SECRET&revise=1') as string;
    expect(out.startsWith('/my-requests/complaint/abc')).toBe(true);
    expect(out).toContain('revise=1');
    expect(out).not.toContain('token');
    expect(out).not.toContain('SECRET');
  });

  it.each([
    ['/portal/c/SLUG123456/verify'],
    ['/portal/c/SLUG123456/verify?type=complaint&id=x'],
    ['/portal?token=T1'],
    ['/portal'],
    ['/portal/verify?token=T1'],
    ['/my-requests'],
    ['/'],
    ['/project-sales/pipeline'],
  ])('%s -> null', (from) => {
    expect(crm(from)).toBeNull();
  });
});
